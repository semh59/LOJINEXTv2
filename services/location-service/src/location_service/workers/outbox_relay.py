"""Outbox relay worker for Location Service."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from sqlalchemy import and_, not_, or_, select, update
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from location_service.broker import EventBroker
from location_service.config import settings
from location_service.database import async_session_factory
from location_service.models import LocationOutboxModel

logger = logging.getLogger("location_service.outbox_relay")

WORKER_ID = f"location-outbox-{uuid.getnode()}"


async def run_outbox_relay(broker: EventBroker, shutdown_event: asyncio.Event | None = None) -> None:
    """Poll the outbox table and publish pending events to the broker."""
    logger.info("Outbox relay worker started (poll_interval=%ds)", settings.outbox_poll_interval_seconds)

    while True:
        if shutdown_event and shutdown_event.is_set():
            logger.info("Outbox relay worker: shutdown signal received, exiting cleanly.")
            return
        try:
            async with async_session_factory() as session:
                await _process_batch(session, broker)
        except asyncio.CancelledError:
            logger.info("Outbox relay worker cancelled")
            return
        except Exception:
            logger.exception("Outbox relay error")

        await asyncio.sleep(settings.outbox_poll_interval_seconds)


async def _process_batch(session: AsyncSession, broker: EventBroker) -> int:
    """Process a batch of pending outbox rows using individual commits with explicit CLAIM state."""
    now = datetime.now(timezone.utc)
    claim_expiry = now + timedelta(minutes=5)
    claim_token = str(uuid.uuid4())

    o2 = aliased(LocationOutboxModel)
    hol_subq = select(1).where(
        o2.partition_key == LocationOutboxModel.partition_key,
        o2.publish_status != "PUBLISHED",
        o2.created_at_utc < LocationOutboxModel.created_at_utc,
    )

    query = (
        select(LocationOutboxModel.outbox_id)
        .where(
            or_(
                and_(
                    LocationOutboxModel.publish_status.in_(["PENDING", "FAILED"]),
                    (LocationOutboxModel.next_attempt_at_utc.is_(None))
                    | (LocationOutboxModel.next_attempt_at_utc <= now),
                ),
                and_(
                    LocationOutboxModel.publish_status == "PUBLISHING",
                    LocationOutboxModel.claim_expires_at_utc.is_not(None),
                    LocationOutboxModel.claim_expires_at_utc <= now,
                ),
            ),
            not_(hol_subq.exists()),
        )
        .order_by(LocationOutboxModel.created_at_utc.asc())
        .limit(settings.outbox_publish_batch_size)
        .with_for_update(skip_locked=True)
    )

    result = await session.execute(query)
    outbox_ids = result.scalars().all()

    if not outbox_ids:
        return 0

    await session.execute(
        update(LocationOutboxModel)
        .where(LocationOutboxModel.outbox_id.in_(outbox_ids))
        .values(
            publish_status="PUBLISHING",
            claim_token=claim_token,
            claimed_by_worker=WORKER_ID,
            claim_expires_at_utc=claim_expiry,
        )
    )
    await session.commit()

    published_count = 0
    for outbox_id in outbox_ids:
        try:
            result = await session.execute(
                select(LocationOutboxModel).where(LocationOutboxModel.outbox_id == outbox_id)
            )
            row = cast(LocationOutboxModel, result.scalar_one_or_none())
            if not row or row.publish_status != "PUBLISHING":
                continue

            payload = json.loads(row.payload_json)

            await broker.publish(
                topic=settings.kafka_topic,
                key=row.aggregate_id,
                payload={
                    "event_id": row.outbox_id,
                    "event_name": row.event_name,
                    "event_version": row.event_version,
                    "aggregate_id": row.aggregate_id,
                    "aggregate_type": row.aggregate_type,
                    "aggregate_version": row.aggregate_version,
                    "payload": payload,
                    "published_at_utc": now.isoformat(),
                },
            )

            row.publish_status = "PUBLISHED"
            row.published_at_utc = now
            row.last_error_code = None
            row.claim_expires_at_utc = None
            row.claim_token = None
            row.claimed_by_worker = None

            await session.commit()
            published_count += 1

        except Exception as e:
            await session.rollback()
            logger.error("Failed to publish outbox row %s: %s", outbox_id, str(e))

            result = await session.execute(
                select(LocationOutboxModel).where(LocationOutboxModel.outbox_id == outbox_id)
            )
            row = cast(LocationOutboxModel, result.scalar_one_or_none())
            if row:
                row.attempt_count += 1
                row.last_error_code = type(e).__name__[:100]
                row.claim_expires_at_utc = None
                row.claim_token = None
                row.claimed_by_worker = None
                if row.attempt_count >= settings.outbox_retry_max:
                    row.publish_status = "DEAD_LETTER"
                else:
                    row.publish_status = "FAILED"
                    # Exponential: 5, 10, 20, 40, 80, 160, 300...
                    base_delay = min(300, 5 * (2 ** (row.attempt_count - 1)))
                    import random

                    jitter = base_delay * 0.1
                    actual_delay = base_delay + random.uniform(-jitter, jitter)
                    row.next_attempt_at_utc = datetime.fromtimestamp(
                        now.timestamp() + max(1, actual_delay), tz=timezone.utc
                    )

                await session.commit()

    if published_count:
        logger.info("Outbox relay: successfully published %d rows", published_count)
    return published_count
