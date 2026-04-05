"""Outbox relay worker for Location Service."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from location_service.broker import EventBroker
from location_service.config import settings
from location_service.database import async_session_factory
from location_service.models import LocationOutboxModel

logger = logging.getLogger("location_service.outbox_relay")


async def run_outbox_relay(broker: EventBroker) -> None:
    """Poll the outbox table and publish pending events to the broker."""
    logger.info("Outbox relay worker started (poll_interval=%ds)", settings.outbox_poll_interval_seconds)

    while True:
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
    """Process a batch of pending outbox rows using individual commits."""
    now = datetime.now(timezone.utc)

    query = (
        select(LocationOutboxModel)
        .where(
            LocationOutboxModel.publish_status.in_(["PENDING", "FAILED"]),
            (LocationOutboxModel.next_attempt_at_utc.is_(None)) | (LocationOutboxModel.next_attempt_at_utc <= now),
        )
        .order_by(LocationOutboxModel.created_at_utc.asc())
        .limit(settings.outbox_publish_batch_size)
        .with_for_update(skip_locked=True)
    )

    result = await session.execute(query)
    rows = result.scalars().all()

    if not rows:
        return 0

    published_count = 0
    for row in rows:
        try:
            # V2.1 Standard: Payload must contain aggregate metadata
            # For Location, we use target_id as aggregate_id
            target_id = row.payload_json.get("target_id") or row.payload_json.get("location_id") or row.outbox_id
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

            # Individual commit per row to guarantee at-least-once delivery
            await session.commit()
            published_count += 1

        except Exception as e:
            await session.rollback()
            logger.error("Failed to publish outbox row %s: %s", row.outbox_id, str(e))

            row.retry_count += 1
            if row.retry_count >= settings.outbox_retry_max:
                row.publish_status = "DEAD_LETTER"
            else:
                row.publish_status = "FAILED"
                backoff = min(2**row.retry_count, 300)
                row.next_attempt_at_utc = datetime.fromtimestamp(now.timestamp() + backoff, tz=timezone.utc)

            session.add(row)
            await session.commit()

    if published_count:
        logger.info("Outbox relay: successfully published %d rows", published_count)
    return published_count
