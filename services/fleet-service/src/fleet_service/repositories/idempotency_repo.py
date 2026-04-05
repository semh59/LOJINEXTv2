"""Idempotency repository (Section 8.9 — create-replay protection)."""

from __future__ import annotations

import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_service.models import FleetIdempotencyRecord
from fleet_service.timestamps import to_utc_naive, utc_now_naive


async def find_existing_record(
    session: AsyncSession, idempotency_key: str, endpoint_fingerprint: str
) -> FleetIdempotencyRecord | None:
    """Check if an idempotency record already exists (replay detection)."""
    stmt = select(FleetIdempotencyRecord).where(
        FleetIdempotencyRecord.idempotency_key == idempotency_key,
        FleetIdempotencyRecord.endpoint_fingerprint == endpoint_fingerprint,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def insert_record(session: AsyncSession, record: FleetIdempotencyRecord) -> None:
    """Insert a new idempotency record after successful create."""
    session.add(record)
    await session.flush()


async def cleanup_expired(session: AsyncSession, now: datetime.datetime | None = None) -> int:
    """Delete expired idempotency records (TTL cleanup — every 6 hours).

    Returns number of rows deleted.
    """
    if now is None:
        now = utc_now_naive()
    else:
        now = to_utc_naive(now)
    stmt = delete(FleetIdempotencyRecord).where(FleetIdempotencyRecord.expires_at_utc < now)
    result = await session.execute(stmt)
    return result.rowcount  # type: ignore[return-value]
