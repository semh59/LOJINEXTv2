"""Outbox relay worker — polls, claims, publishes, retries, dead-letters (Section 15).

Uses outbox_repo.claim_batch (FOR UPDATE SKIP LOCKED) for multi-instance safety.
Each claimed row is finalized individually so one publish outcome doesn't roll back another.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_service.broker import MessageBroker, OutboxMessage
from fleet_service.config import settings
from fleet_service.database import async_session_factory
from fleet_service.models import FleetOutbox
from fleet_service.repositories import outbox_repo
from fleet_service.timestamps import utc_now_naive
from fleet_service.worker_heartbeats import record_worker_heartbeat

logger = logging.getLogger("fleet_service.outbox_relay")

# --- Backoff schedule (Section 15.2) ---

OUTBOX_BASE_BACKOFF = 5
OUTBOX_MAX_BACKOFF = 300


def _next_attempt_at(attempt_count: int) -> datetime:
    """Calculate next retry time using jittered exponential backoff."""
    # Exponential: 5, 10, 20, 40, 80, 160, 300...
    delay = min(OUTBOX_MAX_BACKOFF, OUTBOX_BASE_BACKOFF * (2 ** (attempt_count - 1)))
    jitter = delay * 0.1
    actual_delay = delay + random.uniform(-jitter, jitter)
    return _now_utc() + timedelta(seconds=max(1, actual_delay))


def _now_utc() -> datetime:
    """Current naive UTC timestamp matching the Fleet schema."""
    return utc_now_naive()


def _is_schema_not_ready(exc: Exception) -> bool:
    """Return whether a DB error means the outbox table is not migrated yet."""
    if not isinstance(exc, DBAPIError):
        return False
    message = str(exc).lower()
    return "fleet_outbox" in message and any(
        marker in message for marker in ("does not exist", "undefined table", "relation")
    )


def _build_message(row: FleetOutbox) -> OutboxMessage:
    """Build an OutboxMessage from a FleetOutbox ORM row."""
    return OutboxMessage(
        event_id=row.outbox_id,
        event_name=row.event_name,
        partition_key=row.aggregate_id,
        payload=json.loads(row.payload_json),
        event_version=row.event_version,
        aggregate_type=row.aggregate_type,
        aggregate_id=row.aggregate_id,
    )


# --- Relay batch ---


async def _relay_batch(broker: MessageBroker, batch_size: int) -> int:
    """Claim and publish a batch of outbox rows.

    Uses SELECT ... FOR UPDATE SKIP LOCKED via outbox_repo.claim_batch.
    Each claimed row is finalized in its own transaction.
    """
    async with async_session_factory() as session:
        rows = await outbox_repo.claim_batch(session, batch_size, _now_utc())
        if not rows:
            await session.commit()
            return 0
        # Snapshot IDs before committing the claim
        row_ids = [r.outbox_id for r in rows]
        await session.commit()

    published_count = 0
    for outbox_id in row_ids:
        success = await _publish_single(broker, outbox_id)
        if success:
            published_count += 1
    return published_count


async def _publish_single(broker: MessageBroker, outbox_id: str) -> bool:
    """Attempt to publish and finalize a single outbox event."""
    from fleet_service.observability import correlation_id

    token = correlation_id.set(outbox_id)
    try:
        async with async_session_factory() as session:
            row = await _reload_row(session, outbox_id)
            if row is None:
                logger.warning("Outbox %s: row disappeared before publish", outbox_id)
                return False

            message = _build_message(row)
            now = _now_utc()
            publish_error: Exception | None = None

            try:
                await broker.publish(message)
            except Exception as exc:
                publish_error = exc

            if publish_error is None:
                await outbox_repo.mark_published(session, outbox_id, now)
            else:
                new_attempt_count = row.attempt_count + 1
                if new_attempt_count >= settings.outbox_max_retries:
                    await outbox_repo.mark_dead_letter(session, outbox_id)
                else:
                    next_at = _next_attempt_at(new_attempt_count)
                    await outbox_repo.mark_failed(
                        session,
                        outbox_id,
                        error_code="PUBLISH_ERROR",
                        error_message=str(publish_error)[:200],
                        next_attempt_at=next_at,
                    )
            await session.commit()

        if publish_error is None:
            logger.info(
                "Outbox %s: published event %s for %s/%s",
                message.event_id,
                message.event_name,
                message.aggregate_type,
                message.aggregate_id,
            )
            return True

        if (row.attempt_count + 1) >= settings.outbox_max_retries:
            logger.error(
                "Outbox %s: DEAD_LETTER after %d failures: %s",
                message.event_id,
                row.attempt_count + 1,
                publish_error,
            )
        else:
            logger.warning(
                "Outbox %s: publish failed (attempt %d/%d): %s",
                message.event_id,
                row.attempt_count + 1,
                settings.outbox_max_retries,
                publish_error,
            )
        return False
    finally:
        correlation_id.reset(token)


async def _reload_row(session: AsyncSession, outbox_id: str) -> FleetOutbox | None:
    """Reload a single outbox row by ID (within an open session)."""
    from sqlalchemy import select

    stmt = select(FleetOutbox).where(FleetOutbox.outbox_id == outbox_id).with_for_update()
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# --- Main relay loop ---


async def run_outbox_relay(broker: MessageBroker, shutdown_event: asyncio.Event | None = None) -> None:
    """Main outbox relay loop.

    Runs indefinitely, polling for unpublished events.
    Multiple instances are safe (FOR UPDATE SKIP LOCKED).
    """
    logger.info("Outbox relay starting with broker %s", type(broker).__name__)

    try:
        while True:
            if shutdown_event and shutdown_event.is_set():
                logger.info("Relay: shutdown signal received, exiting cleanly.")
                return

            try:
                published = await _relay_batch(broker, settings.outbox_batch_size)
                if published > 0:
                    logger.info("Relay: published %d events", published)
                await record_worker_heartbeat("outbox-relay")
            except Exception as exc:
                if _is_schema_not_ready(exc):
                    logger.warning("Relay: schema not migrated yet, skipping this interval")
                else:
                    logger.error("Relay: batch error: %s", exc)

            await asyncio.sleep(settings.outbox_poll_interval_seconds)
    finally:
        await broker.close()
