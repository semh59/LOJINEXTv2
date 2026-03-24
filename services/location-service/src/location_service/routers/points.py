"""Endpoints for Location Points (Section 4.10)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from location_service.database import get_db
from location_service.domain.normalization import normalize_en, normalize_tr
from location_service.errors import ProblemDetailError
from location_service.models import LocationPoint
from location_service.schemas import PaginationMeta, PointCreate, PointListResponse, PointResponse, PointUpdate

router = APIRouter(prefix="/v1/points", tags=["points"])


@router.post("", response_model=PointResponse, status_code=201)
async def create_point(payload: PointCreate, session: Annotated[AsyncSession, Depends(get_db)]) -> PointResponse:
    """Create a canonical Location Point."""
    # Check uniqueness of code
    stmt = select(LocationPoint).where(func.lower(LocationPoint.code) == func.lower(payload.code))
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing:
        raise ProblemDetailError(
            status=409,
            code="LOCATION_POINT_CODE_CONFLICT",
            title="Conflict",
            detail=f"Point with code '{payload.code}' already exists.",
        )

    point = LocationPoint(
        code=payload.code.upper(),
        name_tr=payload.name_tr.strip(),
        name_en=payload.name_en.strip(),
        normalized_name_tr=normalize_tr(payload.name_tr),
        normalized_name_en=normalize_en(payload.name_en),
        latitude_6dp=round(payload.latitude_6dp, 6),
        longitude_6dp=round(payload.longitude_6dp, 6),
        is_active=payload.is_active,
    )

    session.add(point)
    await session.commit()
    await session.refresh(point)

    return point  # type: ignore[return-value]


@router.get("/{location_id}", response_model=PointResponse)
async def get_point(location_id: UUID, session: Annotated[AsyncSession, Depends(get_db)]) -> PointResponse:
    """Retrieve a Location Point by ID."""
    stmt = select(LocationPoint).where(LocationPoint.location_id == location_id)
    point = (await session.execute(stmt)).scalar_one_or_none()

    if not point:
        raise ProblemDetailError(
            status=404,
            code="LOCATION_POINT_NOT_FOUND",
            title="Not Found",
            detail=f"Point {location_id} not found.",
        )

    return point  # type: ignore[return-value]


@router.get("", response_model=PointListResponse)
async def list_points(
    session: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    is_active: Annotated[bool | None, Query()] = None,
    search: Annotated[str | None, Query(min_length=2)] = None,
) -> dict[str, object]:
    """List Location Points with optional filtering and pagination."""
    stmt = select(LocationPoint)

    if is_active is not None:
        stmt = stmt.where(LocationPoint.is_active.is_(is_active))

    if search:
        search_norm = normalize_tr(search)
        stmt = stmt.where(
            or_(
                LocationPoint.code.ilike(f"%{search}%"),
                LocationPoint.normalized_name_tr.ilike(f"%{search_norm}%"),
                LocationPoint.normalized_name_en.ilike(f"%{normalize_en(search)}%"),
            )
        )

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_items = (await session.execute(count_stmt)).scalar() or 0
    total_pages = (total_items + limit - 1) // limit if limit > 0 else 0

    # Apply pagination
    stmt = stmt.order_by(LocationPoint.location_id.desc()).offset((page - 1) * limit).limit(limit)
    items = (await session.execute(stmt)).scalars().all()

    return {
        "data": list(items),
        "meta": PaginationMeta(
            page=page,
            per_page=limit,
            total_items=total_items,
            total_pages=total_pages,
            sort="location_id:desc",
        ).model_dump(),
    }


@router.patch("/{location_id}", response_model=PointResponse)
async def update_point(
    location_id: UUID, payload: PointUpdate, session: Annotated[AsyncSession, Depends(get_db)]
) -> PointResponse:
    """Partial update of a Location Point."""
    stmt = select(LocationPoint).where(LocationPoint.location_id == location_id)
    point = (await session.execute(stmt)).scalar_one_or_none()

    if not point:
        raise ProblemDetailError(
            status=404,
            code="LOCATION_POINT_NOT_FOUND",
            title="Not Found",
            detail=f"Point {location_id} not found.",
        )

    # BR-11: Deactivation guard can be implemented if it checks dependencies
    # (e.g. active route pairs). For now, basic DB update.
    update_data = payload.model_dump(exclude_unset=True)

    if "name_tr" in update_data:
        point.name_tr = update_data["name_tr"].strip()
        point.normalized_name_tr = normalize_tr(point.name_tr)

    if "name_en" in update_data:
        point.name_en = update_data["name_en"].strip()
        point.normalized_name_en = normalize_en(point.name_en)

    if "latitude_6dp" in update_data:
        point.latitude_6dp = round(update_data["latitude_6dp"], 6)

    if "longitude_6dp" in update_data:
        point.longitude_6dp = round(update_data["longitude_6dp"], 6)

    if "is_active" in update_data:
        point.is_active = update_data["is_active"]

    point.row_version += 1  # Optimistic lock emulation

    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise ProblemDetailError(
            status=400,
            code="LOCATION_UPDATE_FAILED",
            title="Update Failed",
            detail=str(e),
        )

    await session.refresh(point)
    return point  # type: ignore[return-value]
