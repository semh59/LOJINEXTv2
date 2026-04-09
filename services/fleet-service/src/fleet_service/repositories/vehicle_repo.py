"""Vehicle repository (Section 9 — vehicle CRUD + lifecycle + hard-delete)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_service.models import FleetVehicle, FleetVehicleSpecVersion


async def create_vehicle(session: AsyncSession, vehicle: FleetVehicle) -> FleetVehicle:
    """Insert a new vehicle master row."""
    session.add(vehicle)
    await session.flush()
    return vehicle


async def get_vehicle_by_id(
    session: AsyncSession, vehicle_id: str, *, include_soft_deleted: bool = False
) -> FleetVehicle | None:
    """Fetch a vehicle by ID."""
    stmt = select(FleetVehicle).where(FleetVehicle.vehicle_id == vehicle_id)
    if not include_soft_deleted:
        stmt = stmt.where(FleetVehicle.soft_deleted_at_utc.is_(None))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_vehicle_for_update(session: AsyncSession, vehicle_id: str) -> FleetVehicle | None:
    """SELECT ... FOR UPDATE on vehicle master row (pessimistic lock)."""
    stmt = select(FleetVehicle).where(FleetVehicle.vehicle_id == vehicle_id).with_for_update()
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_vehicle_list(
    session: AsyncSession,
    *,
    status: str | None = None,
    ownership_type: str | None = None,
    q: str | None = None,
    sort: str = "updated_at_desc",
    page: int = 1,
    per_page: int = 20,
    include_inactive: bool = False,
    include_soft_deleted: bool = False,
) -> tuple[list[FleetVehicle], int]:
    """Fetch paginated vehicle list with filters, sort, and total count.

    Section 7.3 default visibility:
    - ACTIVE only by default
    - include_inactive=true → also show INACTIVE rows
    - include_soft_deleted=true → also show soft-deleted rows

    Returns (items, total_count).
    """
    base = select(FleetVehicle)
    count_base = select(func.count()).select_from(FleetVehicle)

    # Soft-deleted visibility
    if not include_soft_deleted:
        base = base.where(FleetVehicle.soft_deleted_at_utc.is_(None))
        count_base = count_base.where(FleetVehicle.soft_deleted_at_utc.is_(None))

    # Default: ACTIVE only; include_inactive shows both ACTIVE and INACTIVE
    if status:
        base = base.where(FleetVehicle.status == status)
        count_base = count_base.where(FleetVehicle.status == status)
    elif not include_inactive:
        base = base.where(FleetVehicle.status == "ACTIVE")
        count_base = count_base.where(FleetVehicle.status == "ACTIVE")

    if ownership_type:
        base = base.where(FleetVehicle.ownership_type == ownership_type)
        count_base = count_base.where(FleetVehicle.ownership_type == ownership_type)

    if q:
        like_pattern = f"%{q}%"
        q_filter = FleetVehicle.plate_raw_current.ilike(like_pattern) | FleetVehicle.asset_code.ilike(like_pattern)
        base = base.where(q_filter)
        count_base = count_base.where(q_filter)

    # Sort
    sort_map: dict[str, Any] = {
        "updated_at_desc": (FleetVehicle.updated_at_utc.desc(), FleetVehicle.vehicle_id.desc()),
        "updated_at_asc": (FleetVehicle.updated_at_utc.asc(), FleetVehicle.vehicle_id.asc()),
        "created_at_desc": (FleetVehicle.created_at_utc.desc(), FleetVehicle.vehicle_id.desc()),
        "created_at_asc": (FleetVehicle.created_at_utc.asc(), FleetVehicle.vehicle_id.asc()),
        "plate_asc": (FleetVehicle.normalized_plate_current.asc(), FleetVehicle.vehicle_id.asc()),
        "plate_desc": (FleetVehicle.normalized_plate_current.desc(), FleetVehicle.vehicle_id.desc()),
    }
    order_cols = sort_map.get(sort, sort_map["updated_at_desc"])
    base = base.order_by(*order_cols)

    # Count
    total_result = await session.execute(count_base)
    total = total_result.scalar_one()

    # Pagination
    offset = (page - 1) * per_page
    base = base.offset(offset).limit(per_page)
    result = await session.execute(base)
    return list(result.scalars().all()), total


async def update_vehicle(session: AsyncSession, vehicle: FleetVehicle) -> FleetVehicle:
    """Flush vehicle mutations to database."""
    await session.flush()
    return vehicle


async def hard_delete_vehicle(session: AsyncSession, vehicle: FleetVehicle) -> None:
    """Physically DELETE a vehicle master row (after passing 4-stage check)."""
    await session.delete(vehicle)
    await session.flush()


async def delete_vehicle_spec_versions(session: AsyncSession, vehicle_id: str) -> int:
    """DELETE all spec versions for a vehicle (plan Step 14 — before master delete).

    Returns number of rows deleted.
    """
    stmt = delete(FleetVehicleSpecVersion).where(FleetVehicleSpecVersion.vehicle_id == vehicle_id)
    result = await session.execute(stmt)
    return result.rowcount or 0


async def get_current_vehicle_spec(session: AsyncSession, vehicle_id: str) -> FleetVehicleSpecVersion | None:
    """Get the current spec version for a vehicle (is_current=True)."""
    stmt = select(FleetVehicleSpecVersion).where(
        FleetVehicleSpecVersion.vehicle_id == vehicle_id,
        FleetVehicleSpecVersion.is_current.is_(True),
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def check_plate_uniqueness(
    session: AsyncSession, normalized_plate: str, *, exclude_vehicle_id: str | None = None
) -> bool:
    """Check if normalized plate is already in use by another non-deleted vehicle.

    Returns True if plate is available (no conflict).
    """
    stmt = (
        select(func.count())
        .select_from(FleetVehicle)
        .where(
            FleetVehicle.normalized_plate_current == normalized_plate,
            FleetVehicle.soft_deleted_at_utc.is_(None),
        )
    )
    if exclude_vehicle_id:
        stmt = stmt.where(FleetVehicle.vehicle_id != exclude_vehicle_id)
    result = await session.execute(stmt)
    return result.scalar_one() == 0


async def check_asset_code_uniqueness(
    session: AsyncSession, asset_code: str, *, exclude_vehicle_id: str | None = None
) -> bool:
    """Check if asset_code is already in use.

    Returns True if asset_code is available.
    """
    stmt = select(func.count()).select_from(FleetVehicle).where(FleetVehicle.asset_code == asset_code)
    if exclude_vehicle_id:
        stmt = stmt.where(FleetVehicle.vehicle_id != exclude_vehicle_id)
    result = await session.execute(stmt)
    return result.scalar_one() == 0
