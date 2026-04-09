"""Outbox relay worker - V8 Section 14.

Publishes domain events from the transactional outbox table to the message broker.

CRITICAL DIFFERENCES FROM ENRICHMENT WORKER:
- SEPARATE backoff schedule: 5s -> 10s -> 30s -> 60s -> 5min
- The counter is CONSECUTIVE failures, NOT total attempt_count.
  If a publish succeeds between failures, the consecutive counter resets.
- 10 CONSECUTIVE failures -> DEAD_LETTER (V8 Section 14.2)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, not_, or_, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import aliased

from trip_service.broker import MessageBroker, OutboxMessage
from trip_service.config import settings
from trip_service.database import async_session_factory
from trip_service.enums import OutboxPublishStatus
from trip_service.models import TripOutbox
from trip_service.observability import (
    OUTBOX_DEAD_LETTER_TOTAL,
    OUTBOX_PUBLISHED_TOTAL,
    get_standard_labels,
)
from trip_service.worker_heartbeats import record_worker_heartbeat

logger = logging.getLogger("trip_service.outbox_relay")

# ---------------------------------------------------------------------------
# V8 Section 14.2 - Outbox relay backoff (NOT enrichment backoff)
# ---------------------------------------------------------------------------

OUTBOX_BACKOFF_SECONDS: list[int] = [
    5,
    10,
    30,
    60,
    300,
]


def _outbox_next_attempt_at(consecutive_failures: int) -> datetime:
    """Calculate next retry time for outbox relay."""
    idx = min(max(consecutive_failures - 1, 0), len(OUTBOX_BACKOFF_SECONDS) - 1)
    delay = OUTBOX_BACKOFF_SECONDS[idx]
    return _now_utc() + timedelta(seconds=delay)


def _now_utc() -> datetime:
    """Current UTC timestamp."""
    return datetime.now(UTC)


def _is_schema_not_ready(exc: Exception) -> bool:
    """Return whether a DB error means the outbox table is not migrated yet."""
    if not isinstance(exc, DBAPIError):
        return False
    message = str(exc).lower()
    return "trip_outbox" in message and any(
        marker in message for marker in ("does not exist", "undefined table", "relation")
    )


def _build_message(row: TripOutbox) -> OutboxMessage:
    return OutboxMessage(
        event_id=row.event_id,
        event_name=row.event_name,
        partition_key=row.partition_key,
        payload=row.payload_json,
        schema_version=row.schema_version,
        aggregate_type=row.aggregate_type,
        aggregate_id=row.aggregate_id,
    )


async def _claim_batch(worker_id: str, batch_size: int) -> tuple[str, list[str]]:
    """Claim a batch of rows and return the shared claim token plus event ids."""
    now = _now_utc()
    claim_ttl = timedelta(seconds=settings.outbox_relay_claim_ttl_seconds)
    claim_token = str(uuid.uuid4())

    async with async_session_factory() as session:
        # -----------------------------------------------------------------------
        # Head-of-Line (HOL) blocking:
        # A row is eligible ONLY IF it is the EARLIEST row for its partition_key
        # that is not yet PUBLISHED. This ensures strict sequential processing.
        # -----------------------------------------------------------------------
        o2 = aliased(TripOutbox)
        hol_subq = select(1).where(
            o2.partition_key == TripOutbox.partition_key,
            o2.publish_status != OutboxPublishStatus.PUBLISHED,
            o2.created_at_utc < TripOutbox.created_at_utc,
        )

        stmt = (
            select(TripOutbox)
            .where(
                or_(
                    TripOutbox.publish_status.in_(
                        [
                            OutboxPublishStatus.PENDING,
                            OutboxPublishStatus.READY,
                            OutboxPublishStatus.FAILED,
                        ]
                    ),
                    and_(
                        TripOutbox.publish_status == OutboxPublishStatus.PUBLISHING,
                        TripOutbox.claim_expires_at_utc < now,
                    ),
                ),
                TripOutbox.next_attempt_at_utc.is_(None) | (TripOutbox.next_attempt_at_utc <= now),
                not_(hol_subq.exists()),
            )
            .order_by(TripOutbox.created_at_utc.asc())
            .with_for_update(skip_locked=True)
            .limit(batch_size)
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

        if not rows:
            return claim_token, []

        for row in rows:
            row.publish_status = OutboxPublishStatus.PUBLISHING
            row.next_attempt_at_utc = None
            row.claim_token = claim_token
            row.claim_expires_at_utc = now + claim_ttl
            row.claimed_by_worker = worker_id
        await session.commit()
        return claim_token, [row.event_id for row in rows]


# ---------------------------------------------------------------------------
# Relay processing
# ---------------------------------------------------------------------------


async def _relay_batch(broker: MessageBroker, worker_id: str, batch_size: int = 20) -> int:
    """Claim and publish a batch of outbox rows.

    Uses SELECT ... FOR UPDATE SKIP LOCKED for multi-instance safety.
    Reclaims PUBLISHING rows that have exceeded their claim TTL.
    Each claimed row is finalized in its own transaction so one publish outcome
    cannot roll back another.
    """
    claim_token, event_ids = await _claim_batch(worker_id, batch_size)
    if not event_ids:
        return 0

    published_count = 0
    for event_id in event_ids:
        success = await _publish_single(broker, event_id, claim_token)
        if success:
            published_count += 1
    return published_count


async def _publish_single(broker: MessageBroker, event_id: str, claim_token: str) -> bool:
    """Attempt to publish and finalize a single claimed outbox event."""
    from trip_service.observability import correlation_id

    token = correlation_id.set(event_id)
    try:
        async with async_session_factory() as session:
            row = (
                await session.execute(
                    select(TripOutbox)
                    .where(
                        TripOutbox.event_id == event_id,
                        TripOutbox.claim_token == claim_token,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()

            if row is None:
                logger.warning("Outbox %s: claim lost before publish finalization", event_id)
                return False

            message = _build_message(row)
            now = _now_utc()
            publish_error: Exception | None = None

            try:
                await broker.publish(message)
            except Exception as exc:  # pragma: no cover - exercised through worker tests
                publish_error = exc

            if publish_error is None:
                row.publish_status = OutboxPublishStatus.PUBLISHED
                row.published_at_utc = now
                row.attempt_count = 0
                row.next_attempt_at_utc = None
                row.last_error_code = None
            else:
                row.attempt_count += 1
                row.last_error_code = str(publish_error)[:100]
                if row.attempt_count >= settings.outbox_relay_max_failures:
                    row.publish_status = OutboxPublishStatus.DEAD_LETTER
                    row.next_attempt_at_utc = None
                else:
                    row.publish_status = OutboxPublishStatus.FAILED
                    row.next_attempt_at_utc = _outbox_next_attempt_at(row.attempt_count)

            row.claim_token = None
            row.claim_expires_at_utc = None
            row.claimed_by_worker = None
            await session.commit()

        if publish_error is None:
            labels = get_standard_labels()
            OUTBOX_PUBLISHED_TOTAL.labels(event_name=message.event_name, **labels).inc()
            logger.info(
                "Outbox %s: published event %s for %s/%s",
                message.event_id,
                message.event_name,
                message.aggregate_type,
                message.aggregate_id,
            )
            return True

        if row.attempt_count >= settings.outbox_relay_max_failures:
            labels = get_standard_labels()
            OUTBOX_DEAD_LETTER_TOTAL.labels(**labels).inc()
            logger.error(
                "Outbox %s: DEAD_LETTER after %d consecutive failures: %s",
                message.event_id,
                row.attempt_count,
                publish_error,
                extra={
                    "alert": "DEAD_LETTER",
                    "event_id": message.event_id,
                    "event_name": message.event_name,
                    "aggregate_id": message.aggregate_id,
                },
            )
        else:
            logger.warning(
                "Outbox %s: publish failed (attempt %d/%d), next retry at %s: %s",
                message.event_id,
                row.attempt_count,
                settings.outbox_relay_max_failures,
                row.next_attempt_at_utc,
                publish_error,
            )
        return False
    finally:
        correlation_id.reset(token)


# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------


async def run_outbox_relay(
    broker: MessageBroker, worker_id: str | None = None, shutdown_event: asyncio.Event | None = None
) -> None:
    """Main outbox relay loop.

    Runs indefinitely, polling for unpublished events.
    Multiple instances are safe (FOR UPDATE SKIP LOCKED).
    """
    if worker_id is None:
        worker_id = f"relay-{uuid.uuid4().hex[:8]}"

    logger.info("Outbox relay %s starting with broker %s", worker_id, type(broker).__name__)

    try:
        while True:
            if shutdown_event and shutdown_event.is_set():
                logger.info("Relay %s: shutdown signal received, exiting cleanly.", worker_id)
                return

            try:
                published = await _relay_batch(broker, worker_id)
                if published > 0:
                    logger.info("Relay %s: published %d events", worker_id, published)
                await record_worker_heartbeat("outbox-relay")
            except Exception as exc:
                if _is_schema_not_ready(exc):
                    logger.warning("Relay %s: schema not migrated yet, skipping this interval", worker_id)
                else:
                    logger.error("Relay %s: batch error: %s", worker_id, exc)

            await asyncio.sleep(settings.outbox_relay_poll_interval_seconds)
    finally:
        await broker.close()
