"""Trailer spec version repository (Phase E — mirror of vehicle_spec_repo).

Handles all direct database queries for fleet_trailer_spec_versions.
"""

from __future__ import annotations

import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_service.models import FleetTrailerSpecVersion


async def get_current_spec(session: AsyncSession, trailer_id: str) -> FleetTrailerSpecVersion | None:
    """Fetch the current spec version (is_current=TRUE) for a trailer."""
    stmt = select(FleetTrailerSpecVersion).where(
        FleetTrailerSpecVersion.trailer_id == trailer_id,
        FleetTrailerSpecVersion.is_current.is_(True),
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_spec_as_of(
    session: AsyncSession, trailer_id: str, at: datetime.datetime
) -> FleetTrailerSpecVersion | None:
    """Fetch the spec version effective at a given timestamp."""
    stmt = (
        select(FleetTrailerSpecVersion)
        .where(
            FleetTrailerSpecVersion.trailer_id == trailer_id,
            FleetTrailerSpecVersion.effective_from_utc <= at,
        )
        .where((FleetTrailerSpecVersion.effective_to_utc.is_(None)) | (FleetTrailerSpecVersion.effective_to_utc > at))
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_max_version_no(session: AsyncSession, trailer_id: str) -> int:
    """Get the maximum version_no for a trailer's spec versions.

    Returns 0 if no spec versions exist.
    """
    stmt = select(func.coalesce(func.max(FleetTrailerSpecVersion.version_no), 0)).where(
        FleetTrailerSpecVersion.trailer_id == trailer_id
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def insert_spec_version(session: AsyncSession, spec: FleetTrailerSpecVersion) -> FleetTrailerSpecVersion:
    """Insert a new spec version row."""
    session.add(spec)
    await session.flush()
    return spec


async def close_current_spec(
    session: AsyncSession,
    trailer_id: str,
    effective_to_utc: datetime.datetime,
) -> int:
    """Close the current spec version by setting is_current=FALSE and effective_to_utc.

    Returns the number of rows updated (0 or 1).
    """
    stmt = (
        update(FleetTrailerSpecVersion)
        .where(
            FleetTrailerSpecVersion.trailer_id == trailer_id,
            FleetTrailerSpecVersion.is_current.is_(True),
        )
        .values(is_current=False, effective_to_utc=effective_to_utc)
    )
    result = await session.execute(stmt)
    return result.rowcount or 0
