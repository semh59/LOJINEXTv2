"""Endpoints for Route Pairs."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from ulid import ULID

from location_service.audit_helpers import _write_audit, _write_outbox, serialize_pair_audit
from location_service.auth import AuthContext, user_auth_dependency
from location_service.database import get_db
from location_service.domain.codes import generate_pair_code
from location_service.domain.normalization import normalize_en, normalize_tr
from location_service.enums import PairStatus
from location_service.errors import (
    ProblemDetailError,
    internal_error,
    invalid_filter_combination,
    point_inactive_for_new_pair,
    route_origin_equals_destination,
    route_pair_already_exists_active,
    route_pair_already_exists_deleted,
    route_pair_already_soft_deleted,
    route_pair_not_found,
    route_pair_soft_deleted,
    route_pair_version_mismatch,
)
from location_service.middleware import check_version_match, set_etag
from location_service.models import LocationPoint, RoutePair
from location_service.query_contracts import build_order_by, resolve_pagination, resolve_sort
from location_service.schemas import (
    PaginationMeta,
    PairCreateRequest,
    PairListResponse,
    PairResponse,
    PairUpdateRequest,
    ProfileCode,
)

router = APIRouter(tags=["pairs"])


_ALLOWED_SORTS = {
    "updated_at_utc:desc",
    "updated_at_utc:asc",
    "created_at_utc:desc",
    "created_at_utc:asc",
    "pair_code:asc",
    "pair_code:desc",
}
_DEFAULT_SORT = "updated_at_utc:desc"


def _constraint_name(exc: IntegrityError) -> str:
    diag = getattr(getattr(exc, "orig", None), "diag", None)
    name = getattr(diag, "constraint_name", None)
    if isinstance(name, str):
        return name
    return str(exc.orig)


def _map_integrity_error(exc: IntegrityError) -> ProblemDetailError:
    name = _constraint_name(exc)
    if "ix_location_route_pairs_live_unique" in name:
        return route_pair_already_exists_active()
    return internal_error()


async def _get_point_by_code(session: AsyncSession, code: str) -> LocationPoint | None:
    return (
        await session.execute(select(LocationPoint).where(func.lower(LocationPoint.code) == func.lower(code)))
    ).scalar_one_or_none()


async def _assert_pair_uniqueness(
    session: AsyncSession,
    *,
    origin_location_id: str,
    destination_location_id: str,
    profile_code: str,
    exclude_pair_id: str | None = None,
) -> None:
    stmt = select(RoutePair).where(
        RoutePair.origin_location_id == origin_location_id,
        RoutePair.destination_location_id == destination_location_id,
        RoutePair.profile_code == profile_code,
    )
    if exclude_pair_id is not None:
        stmt = stmt.where(RoutePair.route_pair_id != exclude_pair_id)

    matches = (await session.execute(stmt)).scalars().all()
    if any(match.pair_status in {PairStatus.ACTIVE, PairStatus.DRAFT} for match in matches):
        raise route_pair_already_exists_active()
    if any(match.pair_status == PairStatus.SOFT_DELETED for match in matches):
        raise route_pair_already_exists_deleted()


async def _get_pair(session: AsyncSession, pair_id: str) -> RoutePair:
    pair = (await session.execute(select(RoutePair).where(RoutePair.route_pair_id == pair_id))).scalar_one_or_none()
    if pair is None:
        raise route_pair_not_found(str(pair_id))
    return pair


async def _get_pair_detail(session: AsyncSession, pair_id: str) -> tuple[RoutePair, LocationPoint, LocationPoint]:
    origin_point = aliased(LocationPoint)
    destination_point = aliased(LocationPoint)
    row = (
        await session.execute(
            select(RoutePair, origin_point, destination_point)
            .join(origin_point, origin_point.location_id == RoutePair.origin_location_id)
            .join(destination_point, destination_point.location_id == RoutePair.destination_location_id)
            .where(RoutePair.route_pair_id == pair_id)
        )
    ).one_or_none()
    if row is None:
        raise route_pair_not_found(str(pair_id))
    pair, origin, destination = row
    return pair, origin, destination


def serialize_pair_response(pair: RoutePair, origin: LocationPoint, destination: LocationPoint) -> PairResponse:
    """Build the public pair response from the pair row plus joined points."""
    return PairResponse(
        pair_id=pair.route_pair_id,
        pair_code=pair.pair_code,
        status=pair.pair_status,
        origin_location_id=pair.origin_location_id,
        destination_location_id=pair.destination_location_id,
        profile_code=ProfileCode(pair.profile_code),
        origin_code=origin.code,
        origin_name_tr=origin.name_tr,
        origin_name_en=origin.name_en,
        destination_code=destination.code,
        destination_name_tr=destination.name_tr,
        destination_name_en=destination.name_en,
        forward_route_id=pair.forward_route_id,
        reverse_route_id=pair.reverse_route_id,
        active_forward_version_no=pair.current_active_forward_version_no,
        active_reverse_version_no=pair.current_active_reverse_version_no,
        draft_forward_version_no=pair.pending_forward_version_no,
        draft_reverse_version_no=pair.pending_reverse_version_no,
        row_version=pair.row_version,
        created_at_utc=pair.created_at_utc,
        updated_at_utc=pair.updated_at_utc,
    )


serialize_pair = serialize_pair_response


@router.post("/api/v1/pairs", response_model=PairResponse, status_code=201)
async def create_pair(
    payload: PairCreateRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(user_auth_dependency)],
) -> PairResponse:
    """Create a new Route Pair."""
    origin = await _get_point_by_code(session, payload.origin_code)
    destination = await _get_point_by_code(session, payload.destination_code)

    if origin is None or destination is None:
        raise ProblemDetailError(
            400,
            "LOCATION_ROUTE_PAIR_INVALID_POINTS",
            "Invalid Points",
            "Origin or destination code does not exist.",
        )

    if origin.location_id == destination.location_id:
        raise route_origin_equals_destination()

    if not origin.is_active or not destination.is_active:
        raise point_inactive_for_new_pair()

    await _assert_pair_uniqueness(
        session,
        origin_location_id=origin.location_id,
        destination_location_id=destination.location_id,
        profile_code=payload.profile_code,
    )

    pair = RoutePair(
        route_pair_id=str(ULID()),
        pair_code=generate_pair_code(),
        pair_status=PairStatus.DRAFT,
        origin_location_id=origin.location_id,
        destination_location_id=destination.location_id,
        profile_code=payload.profile_code,
    )

    try:
        session.add(pair)
        await session.flush()

        # High-fidelity audit & outbox
        new_snapshot = serialize_pair_audit(pair)
        await _write_audit(
            session,
            target_type="PAIR",
            target_id=str(pair.route_pair_id),
            action_type="CREATE",
            actor_id=auth.actor_id,
            actor_role=auth.actor_type,
            new_snapshot=new_snapshot,
        )
        await _write_outbox(
            session,
            event_name="location.pair.created.v1",
            payload={
                "pair_id": str(pair.route_pair_id),
                "pair_code": pair.pair_code,
                "occurred_at_utc": new_snapshot["created_at_utc"],
            },
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _map_integrity_error(exc) from exc
    except Exception as exc:
        await session.rollback()
        raise internal_error() from exc

    await session.refresh(pair)
    set_etag(response, pair.row_version)
    return serialize_pair_response(pair, origin, destination)


@router.get("/api/v1/pairs/{pair_id}", response_model=PairResponse)
async def get_pair(
    pair_id: str,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PairResponse:
    """Retrieve a Route Pair by ID."""
    pair, origin, destination = await _get_pair_detail(session, pair_id)
    set_etag(response, pair.row_version)
    return serialize_pair_response(pair, origin, destination)


@router.get("/api/v1/pairs", response_model=PairListResponse)
async def list_pairs(
    session: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int | None, Query(ge=1, le=100)] = None,
    limit: Annotated[int | None, Query(ge=1, le=100, description="Deprecated alias for per_page.")] = None,
    status: Annotated[PairStatus | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
    profile_code: Annotated[ProfileCode | None, Query()] = None,
    search: Annotated[str | None, Query(min_length=2)] = None,
    sort: Annotated[str | None, Query()] = None,
) -> dict[str, object]:
    """List Route Pairs with optional filtering and pagination."""
    pagination = resolve_pagination(page=page, per_page=per_page, limit=limit)
    sort_contract = resolve_sort(sort=sort, allowed=_ALLOWED_SORTS, default=_DEFAULT_SORT)

    origin_point = aliased(LocationPoint)
    destination_point = aliased(LocationPoint)
    stmt = (
        select(RoutePair, origin_point, destination_point)
        .join(origin_point, origin_point.location_id == RoutePair.origin_location_id)
        .join(destination_point, destination_point.location_id == RoutePair.destination_location_id)
    )

    if status is not None and is_active is True and status != PairStatus.ACTIVE:
        raise invalid_filter_combination("`status` must be ACTIVE when `is_active=true` is provided.")
    if status is not None and is_active is False and status != PairStatus.DRAFT:
        raise invalid_filter_combination("`status` must be DRAFT when `is_active=false` is provided.")

    if status is not None:
        stmt = stmt.where(RoutePair.pair_status == status)
    else:
        stmt = stmt.where(RoutePair.pair_status != PairStatus.SOFT_DELETED)
    if is_active is True:
        stmt = stmt.where(RoutePair.pair_status == PairStatus.ACTIVE)
    elif is_active is False:
        stmt = stmt.where(RoutePair.pair_status == PairStatus.DRAFT)
    if profile_code is not None:
        stmt = stmt.where(RoutePair.profile_code == profile_code)
    if search:
        normalized_search_tr = normalize_tr(search)
        normalized_search_en = normalize_en(search)
        stmt = stmt.where(
            or_(
                RoutePair.pair_code.ilike(f"%{search}%"),
                origin_point.code.ilike(f"%{search}%"),
                destination_point.code.ilike(f"%{search}%"),
                origin_point.normalized_name_tr.ilike(f"%{normalized_search_tr}%"),
                destination_point.normalized_name_tr.ilike(f"%{normalized_search_tr}%"),
                origin_point.normalized_name_en.ilike(f"%{normalized_search_en}%"),
                destination_point.normalized_name_en.ilike(f"%{normalized_search_en}%"),
            )
        )

    order_by = build_order_by(
        sort_contract,
        {
            "updated_at_utc": RoutePair.updated_at_utc,
            "created_at_utc": RoutePair.created_at_utc,
            "pair_code": RoutePair.pair_code,
        },
    )

    total_items = (
        await session.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))
    ).scalar() or 0
    total_pages = (total_items + pagination.per_page - 1) // pagination.per_page if total_items else 0
    rows = (
        await session.execute(
            stmt.order_by(order_by, RoutePair.route_pair_id.desc()).offset(pagination.offset).limit(pagination.per_page)
        )
    ).all()

    return {
        "data": [serialize_pair_response(pair, origin, destination) for pair, origin, destination in rows],
        "meta": PaginationMeta(
            page=pagination.page,
            per_page=pagination.per_page,
            total_items=total_items,
            total_pages=total_pages,
            sort=sort_contract.token,
        ).model_dump(),
    }


@router.patch("/api/v1/pairs/{pair_id}", response_model=PairResponse)
async def update_pair(
    pair_id: str,
    payload: PairUpdateRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(user_auth_dependency)],
) -> PairResponse:
    """Edit route pair properties."""
    pair = await _get_pair(session, pair_id)
    if pair.pair_status == PairStatus.SOFT_DELETED:
        raise route_pair_soft_deleted()

    check_version_match(request, pair.row_version, mismatch_factory=route_pair_version_mismatch)

    changed = False
    if payload.profile_code is not None and payload.profile_code != pair.profile_code:
        if pair.pair_status != PairStatus.DRAFT:
            raise ProblemDetailError(
                422,
                "LOCATION_ROUTE_PAIR_PROFILE_LOCKED",
                "Validation error",
                "Can only change profile for DRAFT pairs.",
            )
        await _assert_pair_uniqueness(
            session,
            origin_location_id=pair.origin_location_id,
            destination_location_id=pair.destination_location_id,
            profile_code=payload.profile_code,
            exclude_pair_id=pair.route_pair_id,
        )
        pair.profile_code = payload.profile_code
        changed = True

    if changed:
        old_snapshot = serialize_pair_audit(pair)
        pair.row_version += 1
        await session.flush()
        new_snapshot = serialize_pair_audit(pair)

        # High-fidelity audit & outbox
        await _write_audit(
            session,
            target_type="PAIR",
            target_id=str(pair.route_pair_id),
            action_type="UPDATE",
            actor_id=auth.actor_id,
            actor_role=auth.actor_type,
            old_snapshot=old_snapshot,
            new_snapshot=new_snapshot,
            request_id=request.headers.get("X-Request-ID"),
        )
        await _write_outbox(
            session,
            event_name="location.pair.updated.v1",
            payload={
                "pair_id": str(pair.route_pair_id),
                "pair_code": pair.pair_code,
                "occurred_at_utc": new_snapshot["updated_at_utc"],
            },
        )

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _map_integrity_error(exc) from exc
    except Exception as exc:
        await session.rollback()
        raise internal_error() from exc

    await session.refresh(pair)
    pair, origin, destination = await _get_pair_detail(session, pair_id)
    set_etag(response, pair.row_version)
    return serialize_pair_response(pair, origin, destination)


@router.delete("/api/v1/pairs/{pair_id}", status_code=status.HTTP_204_NO_CONTENT)
async def soft_delete_pair(
    pair_id: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(user_auth_dependency)],
) -> None:
    """Soft-delete a Route Pair."""
    pair = await _get_pair(session, pair_id)
    if pair.pair_status == PairStatus.SOFT_DELETED:
        raise route_pair_already_soft_deleted()
    check_version_match(request, pair.row_version, mismatch_factory=route_pair_version_mismatch)

    old_snapshot = serialize_pair_audit(pair)
    pair.pair_status = PairStatus.SOFT_DELETED
    pair.row_version += 1
    await session.flush()
    new_snapshot = serialize_pair_audit(pair)

    # High-fidelity audit & outbox
    await _write_audit(
        session,
        target_type="PAIR",
        target_id=str(pair.route_pair_id),
        action_type="SOFT_DELETE",
        actor_id=auth.actor_id,
        actor_role=auth.actor_type,
        old_snapshot=old_snapshot,
        new_snapshot=new_snapshot,
        request_id=request.headers.get("X-Request-ID"),
    )
    await _write_outbox(
        session,
        event_name="location.pair.soft_deleted.v1",
        payload={
            "pair_id": str(pair.route_pair_id),
            "pair_code": pair.pair_code,
            "occurred_at_utc": new_snapshot["updated_at_utc"],
        },
    )

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _map_integrity_error(exc) from exc
    except Exception as exc:
        await session.rollback()
        raise internal_error() from exc
