"""Outbox repository (Section 8.8 + 15.3 — transactional outbox)."""

from __future__ import annotations

import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_service.config import settings
from fleet_service.models import FleetOutbox
from fleet_service.timestamps import to_utc_naive, utc_now_naive


def _claim_deadline(now: datetime.datetime) -> datetime.datetime:
    """Return the retry visibility timeout used when a batch is claimed."""
    claim_window_seconds = max(settings.outbox_poll_interval_seconds * 3, 15)
    return now + datetime.timedelta(seconds=claim_window_seconds)


async def insert_outbox_event(session: AsyncSession, event: FleetOutbox) -> None:
    """Insert a new outbox event (within the same transaction as the domain mutation)."""
    session.add(event)
    await session.flush()


async def dead_letter_by_aggregate(session: AsyncSession, aggregate_type: str, aggregate_id: str) -> int:
    """Move all PENDING/FAILED outbox rows for an aggregate to DEAD_LETTER.

    Used during hard-delete to prevent publishing events for deleted aggregates.
    Returns number of rows affected.
    """
    stmt = (
        update(FleetOutbox)
        .where(
            FleetOutbox.aggregate_type == aggregate_type,
            FleetOutbox.aggregate_id == aggregate_id,
            FleetOutbox.publish_status.in_(["PENDING", "FAILED"]),
        )
        .values(publish_status="DEAD_LETTER")
    )
    result = await session.execute(stmt)
    return result.rowcount  # type: ignore[return-value]


async def claim_batch(
    session: AsyncSession, batch_size: int = 50, now: datetime.datetime | None = None
) -> list[FleetOutbox]:
    """Claim a batch of outbox rows for publishing (FOR UPDATE SKIP LOCKED).

    Only rows with next_attempt_at_utc <= now and status in (PENDING, FAILED).
    """
    if now is None:
        now = utc_now_naive()
    else:
        now = to_utc_naive(now)
    stmt = (
        select(FleetOutbox)
        .where(
            FleetOutbox.publish_status.in_(["PENDING", "FAILED"]),
            FleetOutbox.next_attempt_at_utc <= now,
        )
        .order_by(FleetOutbox.created_at_utc)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    if not rows:
        return rows

    claimed_until = _claim_deadline(now)
    row_ids = [row.outbox_id for row in rows]
    await session.execute(
        update(FleetOutbox)
        .where(FleetOutbox.outbox_id.in_(row_ids))
        .values(next_attempt_at_utc=claimed_until)
    )
    return rows


async def mark_published(session: AsyncSession, outbox_id: str, now: datetime.datetime | None = None) -> None:
    """Mark an outbox row as PUBLISHED."""
    if now is None:
        now = utc_now_naive()
    else:
        now = to_utc_naive(now)
    stmt = (
        update(FleetOutbox)
        .where(FleetOutbox.outbox_id == outbox_id)
        .values(publish_status="PUBLISHED", published_at_utc=now)
    )
    await session.execute(stmt)


async def mark_failed(
    session: AsyncSession,
    outbox_id: str,
    error_code: str,
    error_message: str,
    next_attempt_at: datetime.datetime,
) -> None:
    """Mark an outbox row as FAILED with error details and next retry time."""
    normalized_next_attempt_at = to_utc_naive(next_attempt_at)
    stmt = (
        update(FleetOutbox)
        .where(FleetOutbox.outbox_id == outbox_id)
        .values(
            publish_status="FAILED",
            attempt_count=FleetOutbox.attempt_count + 1,
            last_error_code=error_code,
            last_error_message=error_message,
            next_attempt_at_utc=normalized_next_attempt_at,
        )
    )
    await session.execute(stmt)


async def mark_dead_letter(session: AsyncSession, outbox_id: str) -> None:
    """Move an outbox row to DEAD_LETTER status."""
    stmt = update(FleetOutbox).where(FleetOutbox.outbox_id == outbox_id).values(publish_status="DEAD_LETTER")
    await session.execute(stmt)
