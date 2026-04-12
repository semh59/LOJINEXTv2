"""Outbox repository (Section 8.8 + 15.3 — transactional outbox)."""

from __future__ import annotations

import datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_service.config import settings
from fleet_service.models import FleetOutbox


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
