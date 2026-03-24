"""Outbox relay worker — V8 Section 14.

Publishes domain events from the transactional outbox table to the message broker.

CRITICAL DIFFERENCES FROM ENRICHMENT WORKER:
- SEPARATE backoff schedule: 5s → 10s → 30s → 60s → 5min
- The counter is CONSECUTIVE failures, NOT total attempt_count.
  If a publish succeeds between failures, the consecutive counter resets.
- 10 CONSECUTIVE failures → DEAD_LETTER (V8 Section 14.2)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from trip_service.broker import MessageBroker, OutboxMessage
from trip_service.config import settings
from trip_service.database import async_session_factory
from trip_service.enums import OutboxPublishStatus
from trip_service.models import TripOutbox

logger = logging.getLogger("trip_service.outbox_relay")

# ---------------------------------------------------------------------------
# V8 Section 14.2 — Outbox relay backoff (NOT enrichment backoff)
# ---------------------------------------------------------------------------

OUTBOX_BACKOFF_SECONDS: list[int] = [
    5,  # 5 seconds
    10,  # 10 seconds
    30,  # 30 seconds
    60,  # 60 seconds (1 minute)
    300,  # 5 minutes (cap)
]

MAX_CONSECUTIVE_FAILURES: int = 10


def _outbox_next_attempt_at(attempt_count: int) -> datetime:
    """Calculate next retry time for outbox relay.

    V8 decision: 5s→10s→30s→60s→5min (capped).
    No jitter for outbox (deterministic retries).
    """
    idx = min(attempt_count, len(OUTBOX_BACKOFF_SECONDS) - 1)
    delay = OUTBOX_BACKOFF_SECONDS[idx]
    return _now_utc() + timedelta(seconds=delay)


def _now_utc() -> datetime:
    """Current UTC timestamp."""
    return datetime.now(tz=ZoneInfo("UTC"))


# ---------------------------------------------------------------------------
# Relay processing
# ---------------------------------------------------------------------------


async def _relay_batch(broker: MessageBroker, batch_size: int = 20) -> int:
    """Claim and publish a batch of outbox rows.

    Uses SELECT ... FOR UPDATE SKIP LOCKED for multi-instance safety.
    Returns number of rows processed.
    """
    now = _now_utc()
    published_count = 0

    async with async_session_factory() as session:
        # Select PENDING or FAILED rows that are ready
        stmt = (
            select(TripOutbox)
            .where(
                TripOutbox.publish_status.in_(
                    [
                        OutboxPublishStatus.PENDING,
                        OutboxPublishStatus.FAILED,
                    ]
                ),
                # Only pick up rows ready for attempt
                TripOutbox.next_attempt_at_utc.is_(None) | (TripOutbox.next_attempt_at_utc <= now),
            )
            .order_by(TripOutbox.created_at_utc.asc())
            .with_for_update(skip_locked=True)
            .limit(batch_size)
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

        if not rows:
            return 0

        for row in rows:
            success = await _publish_single(broker, session, row)
            if success:
                published_count += 1

        await session.commit()

    return published_count


async def _publish_single(
    broker: MessageBroker,
    session: AsyncSession,
    row: TripOutbox,
) -> bool:
    """Attempt to publish a single outbox event.

    On success: PUBLISHED, reset attempt_count, record published_at_utc.
    On failure: increment attempt_count (consecutive), schedule retry.
    After MAX_CONSECUTIVE_FAILURES: DEAD_LETTER.

    V8 Section 14.2: The counter tracks CONSECUTIVE failures.
    A success between failures resets the counter.

    Returns True if published successfully.
    """
    now = _now_utc()

    message = OutboxMessage(
        event_id=row.event_id,
        event_name=row.event_name,
        partition_key=row.partition_key,
        payload=row.payload_json,
        schema_version=row.schema_version,
        aggregate_type=row.aggregate_type,
        aggregate_id=row.aggregate_id,
    )

    try:
        await broker.publish(message)

        # SUCCESS: Mark as PUBLISHED, reset consecutive failure counter
        row.publish_status = OutboxPublishStatus.PUBLISHED
        row.published_at_utc = now
        row.attempt_count = 0  # Reset consecutive failure counter on success
        row.next_attempt_at_utc = None
        row.last_error_code = None

        logger.info(
            "Outbox %s: published event %s for %s/%s",
            row.event_id,
            row.event_name,
            row.aggregate_type,
            row.aggregate_id,
        )
        return True

    except Exception as e:
        # FAILURE: Increment consecutive failure counter
        row.attempt_count += 1
        row.last_error_code = str(e)[:100]

        if row.attempt_count >= MAX_CONSECUTIVE_FAILURES:
            # V8 Section 14.2: 10 consecutive failures → DEAD_LETTER
            row.publish_status = OutboxPublishStatus.DEAD_LETTER
            row.next_attempt_at_utc = None
            logger.error(
                "Outbox %s: DEAD_LETTER after %d consecutive failures: %s",
                row.event_id,
                row.attempt_count,
                e,
            )
        else:
            row.publish_status = OutboxPublishStatus.FAILED
            row.next_attempt_at_utc = _outbox_next_attempt_at(row.attempt_count)
            logger.warning(
                "Outbox %s: publish failed (attempt %d/%d), next retry at %s: %s",
                row.event_id,
                row.attempt_count,
                MAX_CONSECUTIVE_FAILURES,
                row.next_attempt_at_utc,
                e,
            )
        return False


# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------


async def run_outbox_relay(broker: MessageBroker, worker_id: str | None = None) -> None:
    """Main outbox relay loop.

    Runs indefinitely, polling for unpublished events.
    Multiple instances are safe (FOR UPDATE SKIP LOCKED).

    Args:
        broker: Injectable message broker implementation.
        worker_id: Optional worker identifier for logging.
    """
    if worker_id is None:
        worker_id = f"relay-{uuid.uuid4().hex[:8]}"

    logger.info("Outbox relay %s starting with broker %s", worker_id, type(broker).__name__)

    try:
        while True:
            try:
                published = await _relay_batch(broker)
                if published > 0:
                    logger.info("Relay %s: published %d events", worker_id, published)
            except Exception as e:
                logger.error("Relay %s: batch error: %s", worker_id, e)

            await asyncio.sleep(settings.outbox_relay_poll_interval_seconds)
    finally:
        await broker.close()
