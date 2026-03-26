"""Endpoints for Route Pairs (Section 4.3)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from location_service.database import get_db
from location_service.domain.codes import generate_pair_code
from location_service.enums import PairStatus
from location_service.errors import (
    ProblemDetailError,
    internal_error,
    route_pair_already_exists_active,
    route_pair_not_found,
    route_pair_soft_deleted,
)
from location_service.models import LocationPoint, RoutePair
from location_service.processing.approval import approve_route_versions
from location_service.schemas import (
    PaginationMeta,
    PairCreateRequest,
    PairListResponse,
    PairResponse,
    PairUpdateRequest,
)

router = APIRouter(prefix="/v1/pairs", tags=["pairs"])


@router.post("", response_model=PairResponse, status_code=201)
async def create_pair(payload: PairCreateRequest, session: Annotated[AsyncSession, Depends(get_db)]) -> PairResponse:
    """Create a new Route Pair."""

    # 1. Validate Points exist
    origin_stmt = select(LocationPoint).where(func.lower(LocationPoint.code) == func.lower(payload.origin_code))
    dest_stmt = select(LocationPoint).where(func.lower(LocationPoint.code) == func.lower(payload.destination_code))

    origin = (await session.execute(origin_stmt)).scalar_one_or_none()
    dest = (await session.execute(dest_stmt)).scalar_one_or_none()

    if not origin or not dest:
        raise ProblemDetailError(
            400,
            "LOCATION_INVALID_POINTS",
            "Invalid Points",
            "Origin or destination code does not exist.",
        )

    # 2. Prevent duplicate active pairs for same O-D
    dup_stmt = select(RoutePair).where(
        RoutePair.origin_location_id == origin.location_id,
        RoutePair.destination_location_id == dest.location_id,
        RoutePair.pair_status.in_([PairStatus.ACTIVE, PairStatus.DRAFT]),
    )
    dup = (await session.execute(dup_stmt)).scalar_one_or_none()

    if dup:
        raise route_pair_already_exists_active()

    pair_code = generate_pair_code()

    pair = RoutePair(
        pair_code=pair_code,
        pair_status=PairStatus.DRAFT,
        origin_location_id=origin.location_id,
        destination_location_id=dest.location_id,
    )

    session.add(pair)

    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise internal_error(str(e))

    await session.refresh(pair)
    return pair  # type: ignore[return-value]


@router.get("/{pair_id}", response_model=PairResponse)
async def get_pair(pair_id: UUID, session: Annotated[AsyncSession, Depends(get_db)]) -> PairResponse:
    """Retrieve a Route Pair by ID."""
    stmt = select(RoutePair).where(RoutePair.route_pair_id == pair_id)
    pair = (await session.execute(stmt)).scalar_one_or_none()

    if not pair:
        raise ProblemDetailError(
            status=404,
            code="LOCATION_ROUTE_PAIR_NOT_FOUND",
            title="Not Found",
            detail=f"Pair {pair_id} not found.",
        )

    return pair  # type: ignore[return-value]


@router.get("", response_model=PairListResponse)
async def list_pairs(
    session: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    status: Annotated[PairStatus | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
) -> dict[str, object]:
    """List Route Pairs with optional filtering and pagination."""
    stmt = select(RoutePair)

    if status is not None:
        stmt = stmt.where(RoutePair.pair_status == status)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_items = (await session.execute(count_stmt)).scalar() or 0
    total_pages = (total_items + limit - 1) // limit if limit > 0 else 0

    stmt = stmt.order_by(RoutePair.route_pair_id.desc()).offset((page - 1) * limit).limit(limit)
    items = (await session.execute(stmt)).scalars().all()

    return {
        "data": list(items),
        "meta": PaginationMeta(
            page=page,
            per_page=limit,
            total_items=total_items,
            total_pages=total_pages,
            sort="pair_id:desc",
        ).model_dump(),
    }


@router.patch("/{pair_id}", response_model=PairResponse)
async def update_pair(
    pair_id: UUID, payload: PairUpdateRequest, session: Annotated[AsyncSession, Depends(get_db)]
) -> PairResponse:
    """Edit route pair properties."""
    stmt = select(RoutePair).where(RoutePair.route_pair_id == pair_id)
    pair = (await session.execute(stmt)).scalar_one_or_none()

    if not pair:
        raise route_pair_not_found(str(pair_id))

    if payload.is_active is not None and payload.is_active is False:
        # If deactivated, it only affects future processing. We just set pair_status = DELETED ?
        # Wait, the spec says "is_active" for a pair does not exist.
        # For pairs, deactivating might mean soft delete. Let's assume soft-deleted.
        if pair.pair_status != PairStatus.SOFT_DELETED:
            pair.pair_status = PairStatus.SOFT_DELETED
    elif payload.is_active is True:
        # Cannot un-delete in V1
        pass

    if payload.profile_code is not None:
        if pair.pair_status != PairStatus.DRAFT:
            raise ProblemDetailError(
                422, "LOCATION_PROFILE_LOCKED", "Validation error", "Can only change profile for DRAFT pairs."
            )
        pair.profile_code = payload.profile_code

    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise internal_error(str(e))

    await session.refresh(pair)
    return pair  # type: ignore[return-value]


@router.post("/{pair_id}/approve", status_code=204)
async def approve_pair(pair_id: UUID) -> None:
    """Promote pending drafts to ACTIVE (Section 6.10)."""
    try:
        await approve_route_versions(pair_id)
    except ValueError as e:
        raise ProblemDetailError(400, "LOCATION_APPROVAL_ERROR", "Validation error", str(e))
    except Exception as e:
        raise internal_error(str(e))
