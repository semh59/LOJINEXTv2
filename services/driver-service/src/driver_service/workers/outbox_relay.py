"""Hardened outbox relay worker for Driver Service."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, not_, or_, select
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from driver_service import database
from driver_service.broker import EventBroker
from driver_service.config import settings
from driver_service.models import DriverOutboxModel
from driver_service.observability import (
    OUTBOX_DEAD_LETTER_TOTAL,
    OUTBOX_EVENTS_PUBLISHED,
    OUTBOX_PUBLISH_FAILURES,
    get_standard_labels,
)
from driver_service.worker_heartbeats import record_worker_heartbeat

logger = logging.getLogger("driver_service.outbox_relay")

WORKER_ID = f"driver-outbox-{uuid.getnode()}"


async def run_outbox_relay(broker: EventBroker, shutdown_event: asyncio.Event | None = None) -> None:
    """Poll the outbox table and publish pending events to the broker."""
    logger.info("Outbox relay worker started (poll_interval=%ds)", settings.outbox_poll_interval_seconds)

    while True:
        if shutdown_event and shutdown_event.is_set():
            logger.info("Outbox relay: shutdown signal received, exiting cleanly.")
            return

        try:
            async with database.async_session_factory() as session:
                await record_worker_heartbeat(session, "outbox_relay", status="RUNNING")
                await session.commit()

            async with database.async_session_factory() as session:
                await _process_batch(session, broker)
        except asyncio.CancelledError:
            logger.info("Outbox relay worker cancelled")
            return
        except Exception:
            logger.exception("Outbox relay error")

        await asyncio.sleep(settings.outbox_poll_interval_seconds)


async def _process_batch(session: AsyncSession, broker: EventBroker) -> int:
    """Process a batch of pending outbox rows with individual commits."""
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    claim_expiry = now + timedelta(minutes=5)
    claim_token = str(uuid.uuid4())

    o2 = aliased(DriverOutboxModel)
    hol_subq = select(1).where(
        o2.partition_key == DriverOutboxModel.partition_key,
        o2.publish_status != "PUBLISHED",
        o2.created_at_utc < DriverOutboxModel.created_at_utc,
    )

    query = (
        select(DriverOutboxModel)
        .where(
            or_(
                DriverOutboxModel.publish_status.in_(["PENDING", "FAILED"]),
                and_(
                    DriverOutboxModel.publish_status == "PUBLISHING",
                    DriverOutboxModel.claim_expires_at_utc <= now,
                ),
            ),
            (DriverOutboxModel.next_attempt_at_utc.is_(None)) | (DriverOutboxModel.next_attempt_at_utc <= now),
            not_(hol_subq.exists()),
        )
        .order_by(DriverOutboxModel.created_at_utc.asc())
        .limit(settings.outbox_publish_batch_size)
        .with_for_update(skip_locked=True)
    )

    result = await session.execute(query)
    rows = result.scalars().all()

    if not rows:
        return 0

    for row in rows:
        row.publish_status = "PUBLISHING"
        row.claim_token = claim_token
        row.claimed_by_worker = WORKER_ID
        row.claim_expires_at_utc = claim_expiry

    await session.commit()

    published_count = 0
    for row_stub in rows:
        from driver_service.observability import correlation_id

        token = correlation_id.set(row_stub.outbox_id)

        try:
            async with database.async_session_factory() as item_session:
                row = await item_session.get(DriverOutboxModel, row_stub.outbox_id, with_for_update=True)
                if not row:
                    logger.warning("Row %s disappeared", row_stub.outbox_id)
                    continue
                if row.publish_status == "PUBLISHED":
                    logger.info("Row %s already published", row_stub.outbox_id)
                    continue

                try:
                    payload = json.loads(row.payload_json)
                    partition_key = row.partition_key or row.driver_id or "unknown"

                    await broker.publish(
                        topic=settings.kafka_topic,
                        key=partition_key,
                        payload={
                            "event_name": row.event_name,
                            "event_version": row.event_version,
                            "aggregate_id": row.aggregate_id,
                            "aggregate_type": row.aggregate_type,
                            "aggregate_version": row.aggregate_version,
                            "data": payload,
                            "published_at_utc": now.isoformat(),
                        },
                    )
                    row.publish_status = "PUBLISHED"
                    row.published_at_utc = now
                    row.claim_expires_at_utc = None
                    row.claim_token = None
                    row.claimed_by_worker = None

                    labels = get_standard_labels()
                    OUTBOX_EVENTS_PUBLISHED.labels(event_name=row.event_name, **labels).inc()
                    published_count += 1
                    await item_session.commit()

                except Exception as exc:
                    await item_session.rollback()

                    async with database.async_session_factory() as fail_session:
                        row = await fail_session.get(DriverOutboxModel, row_stub.outbox_id, with_for_update=True)
                        if row:
                            row.attempt_count += 1
                            row.last_error_code = type(exc).__name__[:100]
                            row.claim_expires_at_utc = None
                            row.claim_token = None
                            row.claimed_by_worker = None

                            if row.attempt_count >= settings.outbox_retry_max:
                                row.publish_status = "DEAD_LETTER"
                                logger.error("Outbox row %s moved to DEAD_LETTER", row.outbox_id)
                                dl_labels = get_standard_labels()
                                OUTBOX_DEAD_LETTER_TOTAL.labels(**dl_labels).inc()
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

                            await fail_session.commit()

                    labels = get_standard_labels()
                    OUTBOX_PUBLISH_FAILURES.labels(event_name=row_stub.event_name, **labels).inc()
        finally:
            correlation_id.reset(token)

    if published_count:
        logger.info("Outbox relay: published %d / %d rows", published_count, len(rows))
    return published_count
