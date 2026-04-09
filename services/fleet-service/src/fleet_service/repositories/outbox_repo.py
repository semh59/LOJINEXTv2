"""Outbox repository (Section 8.8 + 15.3 — transactional outbox)."""

from __future__ import annotations

import datetime

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from fleet_service.config import settings
from fleet_service.models import FleetOutbox
from fleet_service.timestamps import to_utc_naive, utc_now_naive


def _claim_deadline(now: datetime.datetime) -> datetime.datetime:
    """Return the retry visibility timeout used when a batch is claimed."""
    claim_window_seconds = max(settings.outbox_poll_interval_seconds * 3, 15)
    return now + datetime.timedelta(seconds=claim_window_seconds)


async def insert_outbox_event(session: AsyncSession, event: FleetOutbox) -> None:
    """Insert a new outbox event with 512KB safety guard."""
    if event.payload_json and len(event.payload_json) > 512_000:
        raise ValueError(f"Outbox payload exceeds 512KB safety limit ({len(event.payload_json)} bytes)")
    session.add(event)
    await session.flush()


async def dead_letter_by_aggregate(session: AsyncSession, aggregate_type: str, aggregate_id: str) -> int:
    """Move all PENDING/FAILED/PUBLISHING outbox rows for an aggregate to DEAD_LETTER.

    Used during hard-delete to prevent publishing events for deleted aggregates.
    Returns number of rows affected.
    """
    stmt = (
        update(FleetOutbox)
        .where(
            FleetOutbox.aggregate_type == aggregate_type,
            FleetOutbox.aggregate_id == aggregate_id,
            FleetOutbox.publish_status.in_(["PENDING", "FAILED", "PUBLISHING"]),
        )
        .values(
            publish_status="DEAD_LETTER",
            claim_expires_at_utc=None,
            claim_token=None,
            claimed_by_worker=None,
        )
    )
    result = await session.execute(stmt)
    return result.rowcount or 0


async def claim_batch(
    session: AsyncSession, batch_size: int = 50, now: datetime.datetime | None = None
) -> list[FleetOutbox]:
    """Claim a batch of outbox rows for publishing (FOR UPDATE SKIP LOCKED).

    Only rows with next_attempt_at_utc <= now and status in (PENDING, FAILED),
    or rows stuck in PUBLISHING where claim_expires_at_utc < now.
    """
    if now is None:
        now = utc_now_naive()
    else:
        now = to_utc_naive(now)
    # -----------------------------------------------------------------------
    # Head-of-Line (HOL) blocking:
    # Ensures only the earliest available event for a partition is claimed.
    # -----------------------------------------------------------------------
    from sqlalchemy import not_
    from sqlalchemy.orm import aliased

    o2 = aliased(FleetOutbox)
    hol_subq = select(1).where(
        o2.partition_key == FleetOutbox.partition_key,
        o2.publish_status != "PUBLISHED",
        o2.created_at_utc < FleetOutbox.created_at_utc,
    )

    stmt = (
        select(FleetOutbox)
        .where(
            or_(
                and_(
                    FleetOutbox.publish_status.in_(["PENDING", "FAILED"]),
                    FleetOutbox.next_attempt_at_utc <= now,
                ),
                and_(
                    FleetOutbox.publish_status == "PUBLISHING",
                    FleetOutbox.claim_expires_at_utc.is_not(None),
                    FleetOutbox.claim_expires_at_utc < now,
                ),
            ),
            not_(hol_subq.exists()),
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
    claim_token = str(ULID())
    await session.execute(
        update(FleetOutbox)
        .where(FleetOutbox.outbox_id.in_(row_ids))
        .values(
            publish_status="PUBLISHING",
            next_attempt_at_utc=claimed_until,
            claim_expires_at_utc=claimed_until,
            claim_token=claim_token,
            claimed_by_worker=settings.service_name,
        )
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
        .values(
            publish_status="PUBLISHED",
            published_at_utc=now,
            claim_expires_at_utc=None,
            claim_token=None,
            claimed_by_worker=None,
        )
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
            claim_expires_at_utc=None,
            claim_token=None,
            claimed_by_worker=None,
        )
    )
    await session.execute(stmt)


async def mark_dead_letter(session: AsyncSession, outbox_id: str) -> None:
    """Move an outbox row to DEAD_LETTER status."""
    stmt = (
        update(FleetOutbox)
        .where(FleetOutbox.outbox_id == outbox_id)
        .values(
            publish_status="DEAD_LETTER",
            claim_expires_at_utc=None,
            claim_token=None,
            claimed_by_worker=None,
        )
    )
    await session.execute(stmt)
