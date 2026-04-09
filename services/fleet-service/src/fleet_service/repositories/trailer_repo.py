"""Trailer repository (Phase E — mirror of vehicle_repo).

Handles all direct database queries for fleet_trailers.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_service.models import FleetTrailer, FleetTrailerSpecVersion


async def create_trailer(session: AsyncSession, trailer: FleetTrailer) -> FleetTrailer:
    """Insert a new trailer master row."""
    session.add(trailer)
    await session.flush()
    return trailer


async def get_trailer_by_id(
    session: AsyncSession, trailer_id: str, *, include_soft_deleted: bool = False
) -> FleetTrailer | None:
    """Fetch a trailer by ID."""
    stmt = select(FleetTrailer).where(FleetTrailer.trailer_id == trailer_id)
    if not include_soft_deleted:
        stmt = stmt.where(FleetTrailer.soft_deleted_at_utc.is_(None))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_trailer_for_update(session: AsyncSession, trailer_id: str) -> FleetTrailer | None:
    """SELECT ... FOR UPDATE on trailer master row (pessimistic lock)."""
    stmt = select(FleetTrailer).where(FleetTrailer.trailer_id == trailer_id).with_for_update()
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_trailer_list(
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
) -> tuple[list[FleetTrailer], int]:
    """Fetch paginated trailer list with filters, sort, and total count.

    Returns (items, total_count).
    """
    base = select(FleetTrailer)
    count_base = select(func.count()).select_from(FleetTrailer)

    if not include_soft_deleted:
        base = base.where(FleetTrailer.soft_deleted_at_utc.is_(None))
        count_base = count_base.where(FleetTrailer.soft_deleted_at_utc.is_(None))

    if status:
        base = base.where(FleetTrailer.status == status)
        count_base = count_base.where(FleetTrailer.status == status)
    elif not include_inactive:
        base = base.where(FleetTrailer.status == "ACTIVE")
        count_base = count_base.where(FleetTrailer.status == "ACTIVE")

    if ownership_type:
        base = base.where(FleetTrailer.ownership_type == ownership_type)
        count_base = count_base.where(FleetTrailer.ownership_type == ownership_type)

    if q:
        like_pattern = f"%{q}%"
        q_filter = FleetTrailer.plate_raw_current.ilike(like_pattern) | FleetTrailer.asset_code.ilike(like_pattern)
        base = base.where(q_filter)
        count_base = count_base.where(q_filter)

    sort_map: dict[str, Any] = {
        "updated_at_desc": (FleetTrailer.updated_at_utc.desc(), FleetTrailer.trailer_id.desc()),
        "updated_at_asc": (FleetTrailer.updated_at_utc.asc(), FleetTrailer.trailer_id.asc()),
        "created_at_desc": (FleetTrailer.created_at_utc.desc(), FleetTrailer.trailer_id.desc()),
        "created_at_asc": (FleetTrailer.created_at_utc.asc(), FleetTrailer.trailer_id.asc()),
        "plate_asc": (FleetTrailer.normalized_plate_current.asc(), FleetTrailer.trailer_id.asc()),
        "plate_desc": (FleetTrailer.normalized_plate_current.desc(), FleetTrailer.trailer_id.desc()),
    }
    order_cols = sort_map.get(sort, sort_map["updated_at_desc"])
    base = base.order_by(*order_cols)

    total_result = await session.execute(count_base)
    total = total_result.scalar_one()

    offset = (page - 1) * per_page
    base = base.offset(offset).limit(per_page)
    result = await session.execute(base)
    return list(result.scalars().all()), total


async def update_trailer(session: AsyncSession, trailer: FleetTrailer) -> FleetTrailer:
    """Flush trailer mutations to database."""
    await session.flush()
    return trailer


async def hard_delete_trailer(session: AsyncSession, trailer: FleetTrailer) -> None:
    """Physically DELETE a trailer master row."""
    await session.delete(trailer)
    await session.flush()


async def delete_trailer_spec_versions(session: AsyncSession, trailer_id: str) -> int:
    """DELETE all spec versions for a trailer (before master delete).

    Returns number of rows deleted.
    """
    stmt = delete(FleetTrailerSpecVersion).where(FleetTrailerSpecVersion.trailer_id == trailer_id)
    result = await session.execute(stmt)
    return result.rowcount or 0


async def get_current_trailer_spec(session: AsyncSession, trailer_id: str) -> FleetTrailerSpecVersion | None:
    """Get the current spec version for a trailer (is_current=True)."""
    stmt = select(FleetTrailerSpecVersion).where(
        FleetTrailerSpecVersion.trailer_id == trailer_id,
        FleetTrailerSpecVersion.is_current.is_(True),
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def check_plate_uniqueness(
    session: AsyncSession, normalized_plate: str, *, exclude_trailer_id: str | None = None
) -> bool:
    """Check if normalized plate is already in use by another non-deleted trailer.

    Returns True if plate is available.
    """
    stmt = (
        select(func.count())
        .select_from(FleetTrailer)
        .where(
            FleetTrailer.normalized_plate_current == normalized_plate,
            FleetTrailer.soft_deleted_at_utc.is_(None),
        )
    )
    if exclude_trailer_id:
        stmt = stmt.where(FleetTrailer.trailer_id != exclude_trailer_id)
    result = await session.execute(stmt)
    return result.scalar_one() == 0


async def check_asset_code_uniqueness(
    session: AsyncSession, asset_code: str, *, exclude_trailer_id: str | None = None
) -> bool:
    """Check if asset_code is already in use.

    Returns True if asset_code is available.
    """
    stmt = select(func.count()).select_from(FleetTrailer).where(FleetTrailer.asset_code == asset_code)
    if exclude_trailer_id:
        stmt = stmt.where(FleetTrailer.trailer_id != exclude_trailer_id)
    result = await session.execute(stmt)
    return result.scalar_one() == 0
