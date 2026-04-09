"""Outbox relay worker for Location Service."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from location_service.broker import EventBroker
from location_service.config import settings
from location_service.database import async_session_factory
from location_service.models import LocationOutboxModel

logger = logging.getLogger("location_service.outbox_relay")


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
    row = None

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
            )
        )
        .order_by(LocationOutboxModel.created_at_utc.asc())
        .limit(settings.outbox_publish_batch_size)
        .with_for_update(skip_locked=True)
    )

    result = await session.execute(query)
    outbox_ids = result.scalars().all()

    if not outbox_ids:
        return 0

    claim_expiry = now + timedelta(minutes=5)

    # Claim the batch atomically
    await session.execute(
        update(LocationOutboxModel)
        .where(LocationOutboxModel.outbox_id.in_(outbox_ids))
        .values(publish_status="PUBLISHING", claim_expires_at_utc=claim_expiry)
    )
    await session.commit()

    published_count = 0
    for outbox_id in outbox_ids:
        try:
            # Reload row within its own transaction
            result = await session.execute(
                select(LocationOutboxModel).where(LocationOutboxModel.outbox_id == outbox_id)
            )
            row = cast(LocationOutboxModel, result.scalar_one_or_none())
            if not row or row.publish_status != "PUBLISHING":
                continue

            # V2.1 Standard: Payload must contain aggregate metadata
            # For Location, we use target_id as aggregate_id
            target_id = (
                row.payload_json.get("target_id")
                or row.payload_json.get("location_id")
                or row.payload_json.get("pair_id")
                or row.payload_json.get("route_pair_id")
                or row.outbox_id
            )
            target_type = row.payload_json.get("target_type") or "LOCATION"

            await broker.publish(
                topic=settings.kafka_topic,
                key=target_id,  # Partition by aggregate_id
                payload={
                    "event_id": row.outbox_id,
                    "event_name": row.event_name,
                    "event_version": row.event_version,
                    "aggregate_id": target_id,
                    "aggregate_type": target_type,
                    "payload": row.payload_json,
                    "published_at_utc": now.isoformat(),
                },
            )

            row.publish_status = "PUBLISHED"
            row.published_at_utc = now
            row.last_error_code = None
            row.claim_expires_at_utc = None

            # Individual commit per row to guarantee at-least-once delivery
            await session.commit()
            published_count += 1

        except Exception as e:
            await session.rollback()
            logger.error("Failed to publish outbox row %s: %s", outbox_id, str(e))

            # Reload to fail the row
            result = await session.execute(
                select(LocationOutboxModel).where(LocationOutboxModel.outbox_id == outbox_id)
            )
            row = cast(LocationOutboxModel, result.scalar_one_or_none())
            if row:
                row.retry_count += 1
                row.last_error_code = type(e).__name__
                row.claim_expires_at_utc = None
                if row.retry_count >= settings.outbox_retry_max:
                    row.publish_status = "DEAD_LETTER"
                else:
                    row.publish_status = "FAILED"
                    backoff = min(2**row.retry_count, 300)
                    row.next_attempt_at_utc = datetime.fromtimestamp(now.timestamp() + backoff, tz=timezone.utc)

                await session.commit()

    if published_count:
        logger.info("Outbox relay: successfully published %d rows", published_count)
    return published_count
