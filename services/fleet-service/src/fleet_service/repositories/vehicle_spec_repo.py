"""Vehicle spec version repository (Phase D — Section 8.4).

Handles all direct database queries for fleet_vehicle_spec_versions.
"""

from __future__ import annotations

import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_service.models import FleetVehicleSpecVersion


async def get_current_spec(session: AsyncSession, vehicle_id: str) -> FleetVehicleSpecVersion | None:
    """Fetch the current spec version (is_current=TRUE) for a vehicle."""
    stmt = select(FleetVehicleSpecVersion).where(
        FleetVehicleSpecVersion.vehicle_id == vehicle_id,
        FleetVehicleSpecVersion.is_current.is_(True),
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_spec_as_of(
    session: AsyncSession, vehicle_id: str, at: datetime.datetime
) -> FleetVehicleSpecVersion | None:
    """Fetch the spec version effective at a given timestamp.

    Window match: effective_from_utc <= at AND (effective_to_utc IS NULL OR effective_to_utc > at)
    """
    stmt = (
        select(FleetVehicleSpecVersion)
        .where(
            FleetVehicleSpecVersion.vehicle_id == vehicle_id,
            FleetVehicleSpecVersion.effective_from_utc <= at,
        )
        .where((FleetVehicleSpecVersion.effective_to_utc.is_(None)) | (FleetVehicleSpecVersion.effective_to_utc > at))
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_max_version_no(session: AsyncSession, vehicle_id: str) -> int:
    """Get the maximum version_no for a vehicle's spec versions.

    Returns 0 if no spec versions exist.
    """
    stmt = select(func.coalesce(func.max(FleetVehicleSpecVersion.version_no), 0)).where(
        FleetVehicleSpecVersion.vehicle_id == vehicle_id
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def insert_spec_version(session: AsyncSession, spec: FleetVehicleSpecVersion) -> FleetVehicleSpecVersion:
    """Insert a new spec version row."""
    session.add(spec)
    await session.flush()
    return spec


async def close_current_spec(
    session: AsyncSession,
    vehicle_id: str,
    effective_to_utc: datetime.datetime,
) -> int:
    """Close the current spec version by setting is_current=FALSE and effective_to_utc.

    Returns the number of rows updated (0 or 1).
    """
    stmt = (
        update(FleetVehicleSpecVersion)
        .where(
            FleetVehicleSpecVersion.vehicle_id == vehicle_id,
            FleetVehicleSpecVersion.is_current.is_(True),
        )
        .values(is_current=False, effective_to_utc=effective_to_utc)
    )
    result = await session.execute(stmt)
    return result.rowcount or 0
