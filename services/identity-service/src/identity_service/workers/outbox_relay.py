"""Outbox relay worker for Identity Service."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity_service.broker import EventBroker
from identity_service.config import settings
from identity_service.database import async_session_factory
from identity_service.models import IdentityOutboxModel

logger = logging.getLogger("identity_service.outbox_relay")


async def run_outbox_relay(broker: EventBroker) -> None:
    """Poll the outbox table and publish pending events to the broker."""
    logger.info(
        "Outbox relay worker started (poll_interval=%ds)",
        settings.outbox_poll_interval_seconds,
    )

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
    """Process a batch of pending outbox rows with individual commits."""
    now = datetime.now(timezone.utc)

    # Standard V2.1 query with row-level locking
    query = (
        select(IdentityOutboxModel)
        .where(
            IdentityOutboxModel.publish_status.in_(["PENDING", "FAILED"]),
            (IdentityOutboxModel.next_attempt_at_utc.is_(None))
            | (IdentityOutboxModel.next_attempt_at_utc <= now),
        )
        .order_by(IdentityOutboxModel.created_at_utc.asc())
        .limit(settings.outbox_publish_batch_size)
        .with_for_update(skip_locked=True)
    )

    result = await session.execute(query)
    rows = result.scalars().all()

    if not rows:
        return 0

    published_count = 0
    for row in rows:
        # Each row is processed in its own autonomous sub-transaction loop if needed,
        # but here we use the outer session and commit PER ROW to ensure
        # that one failure doesn't rollback others.
        try:
            payload = json.loads(row.payload_json)

            # V2.1 Requirement: Use partition_key if available, fallback to aggregate_id
            partition_key = (
                row.partition_key
                or row.aggregate_id
                or payload.get("user_id", "unknown")
            )

            await broker.publish(
                topic=settings.kafka_topic,
                key=partition_key,
                payload={
                    "event_name": row.event_name,
                    "event_version": row.event_version,
                    "aggregate_id": row.aggregate_id,
                    "aggregate_type": row.aggregate_type,
                    "data": payload,
                    "published_at_utc": now.isoformat(),
                },
            )
            row.publish_status = "PUBLISHED"
            row.published_at_utc = now
            published_count += 1

            # Commit immediately after successful publish
            await session.commit()
            # Re-fetch or continue in same session is fine for small batches,
            # but we must ensure we don't lose the cursor of 'rows'.
            # Since we have unique row objects, we can proceed.

        except Exception:
            # Rollback the specific row change, then update status and commit AGAIN
            await session.rollback()

            row.retry_count += 1
            if row.retry_count >= settings.outbox_retry_max:
                row.publish_status = "DEAD_LETTER"
                logger.error(
                    "Outbox row %s moved to DEAD_LETTER after %d retries",
                    row.outbox_id,
                    row.retry_count,
                )
            else:
                row.publish_status = "FAILED"
                backoff = min(2**row.retry_count, 300)
                row.next_attempt_at_utc = datetime.fromtimestamp(
                    now.timestamp() + backoff, tz=timezone.utc
                )

            # Re-add to session because rollback might have detached it
            session.add(row)
            await session.commit()

    if published_count:
        logger.info("Outbox relay: published %d / %d rows", published_count, len(rows))
    return published_count
