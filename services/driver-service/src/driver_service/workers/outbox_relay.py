"""Hardened outbox relay worker for Driver Service."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from driver_service import database
from driver_service.broker import EventBroker
from driver_service.config import settings
from driver_service.models import DriverOutboxModel
from driver_service.observability import OUTBOX_EVENTS_PUBLISHED, OUTBOX_PUBLISH_FAILURES, get_standard_labels
from driver_service.worker_heartbeats import record_worker_heartbeat

logger = logging.getLogger("driver_service.outbox_relay")


async def run_outbox_relay(broker: EventBroker, shutdown_event: asyncio.Event | None = None) -> None:
    """Poll the outbox table and publish pending events to the broker."""
    logger.info("Outbox relay worker started (poll_interval=%ds)", settings.outbox_poll_interval_seconds)

    while True:
        if shutdown_event and shutdown_event.is_set():
            logger.info("Outbox relay: shutdown signal received, exiting cleanly.")
            return

        try:
            async with database.async_session_factory() as session:
                # Record heartbeat
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
    now = datetime.now(timezone.utc)
    claim_ttl = 300  # 5 minutes

    # Standard V2.1 query with row-level locking and stale claim recovery
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
        )
        .order_by(DriverOutboxModel.created_at_utc.asc())
        .limit(settings.outbox_publish_batch_size)
        .with_for_update(skip_locked=True)
    )

    result = await session.execute(query)
    rows = result.scalars().all()
    logger.info("Found %d rows to process", len(rows))

    if not rows:
        return 0

    # 1. Mark as PUBLISHING (Claiming)
    for row in rows:
        row.publish_status = "PUBLISHING"
        row.claim_expires_at_utc = datetime.fromtimestamp(now.timestamp() + claim_ttl, tz=timezone.utc)

    await session.commit()
    # After commit, rows are detached. We need to process them one by one in new transactions.

    published_count = 0
    for row_stub in rows:
        from driver_service.observability import correlation_id

        token = correlation_id.set(row_stub.outbox_id)

        try:
            async with database.async_session_factory() as item_session:
                # Re-fetch the row to be sure and lock it again for the final update
                row = await item_session.get(DriverOutboxModel, row_stub.outbox_id, with_for_update=True)
                if not row:
                    logger.warning("Row %s disappeared", row_stub.outbox_id)
                    continue
                if row.publish_status == "PUBLISHED":
                    logger.info("Row %s already published", row_stub.outbox_id)
                    continue

                logger.info("Processing row %s with status %s", row.outbox_id, row.publish_status)

                try:
                    payload = json.loads(row.payload_json)
                    partition_key = row.partition_key or row.driver_id or "unknown"

                    await broker.publish(
                        topic=settings.kafka_topic,
                        key=partition_key,
                        payload={
                            "event_name": row.event_name,
                            "event_version": row.event_version,
                            "aggregate_id": row.driver_id,
                            "aggregate_type": "DRIVER",
                            "data": payload,
                            "published_at_utc": now.isoformat(),
                        },
                    )
                    row.publish_status = "PUBLISHED"
                    row.published_at_utc = now
                    row.claim_expires_at_utc = None

                    labels = get_standard_labels()
                    OUTBOX_EVENTS_PUBLISHED.labels(event_name=row.event_name, **labels).inc()
                    published_count += 1
                    await item_session.commit()

                except Exception as exc:
                    await item_session.rollback()

                    # Open a fresh session to record the failure consistently
                    async with database.async_session_factory() as fail_session:
                        row = await fail_session.get(DriverOutboxModel, row_stub.outbox_id, with_for_update=True)
                        if row:
                            row.retry_count += 1
                            row.last_error = str(exc)[:500]
                            row.claim_expires_at_utc = None

                            if row.retry_count >= settings.outbox_retry_max:
                                row.publish_status = "DEAD_LETTER"
                                logger.error("Outbox row %s moved to DEAD_LETTER", row.outbox_id)
                            else:
                                row.publish_status = "FAILED"
                                backoff = min(2**row.retry_count, 300)
                                row.next_attempt_at_utc = datetime.fromtimestamp(
                                    now.timestamp() + backoff, tz=timezone.utc
                                )

                            await fail_session.commit()

                    labels = get_standard_labels()
                    OUTBOX_PUBLISH_FAILURES.labels(event_name=row_stub.event_name, **labels).inc()
        finally:
            correlation_id.reset(token)

    if published_count:
        logger.info("Outbox relay: published %d / %d rows", published_count, len(rows))
    return published_count
