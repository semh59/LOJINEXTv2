"""Endpoints for Location Points."""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from location_service.audit_helpers import (
    _write_audit,
    _write_outbox,
    serialize_point,
)
from location_service.auth import user_auth_dependency, AuthContext
from location_service.database import get_db
from location_service.domain.normalization import normalize_en, normalize_tr
from location_service.enums import PairStatus
from location_service.errors import (
    point_code_conflict,
    point_coordinate_conflict,
    point_immutable_field_modification,
    point_in_use_by_active_pair,
    point_invalid_coordinates,
    point_name_blank,
    point_name_conflict,
    point_not_found,
    request_validation_error,
)
from location_service.middleware import check_version_match, set_etag
from location_service.models import LocationPoint, RoutePair
from location_service.query_contracts import build_order_by, resolve_pagination, resolve_sort
from location_service.schemas import (
    PaginationMeta,
    PointCreate,
    PointListResponse,
    PointResponse,
    PointUpdate,
)

router = APIRouter(prefix="/points", tags=["points"])


_CODE_PATTERN = re.compile(r"^[A-Z0-9_]{2,32}$")
_COORDINATE_CONSTRAINTS = {
    "uq_location_points_lat_lng",
}
_INVALID_COORDINATE_CONSTRAINTS = {
    "chk_location_points_lat",
    "chk_location_points_lng",
    "chk_location_points_not_null_island",
}
_NAME_CONSTRAINTS = {
    "location_points_normalized_name_tr_key",
    "location_points_normalized_name_en_key",
}
_CODE_CONSTRAINTS = {
    "location_points_code_key",
    "chk_location_points_code_format",
}
_ALLOWED_SORTS = {
    "updated_at_utc:desc",
    "updated_at_utc:asc",
    "created_at_utc:desc",
    "created_at_utc:asc",
    "code:asc",
    "code:desc",
}
_DEFAULT_SORT = "updated_at_utc:desc"


def _strip_name(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise point_name_blank()
    return stripped


def _validate_code(code: str) -> str:
    normalized = code.upper()
    if _CODE_PATTERN.fullmatch(normalized) is None:
        raise request_validation_error(
            [{"field": "body.code", "message": "Point code must match ^[A-Z0-9_]{2,32}$.", "type": "value_error"}]
        )
    return normalized


def _validate_coordinates(latitude: float, longitude: float) -> tuple[float, float]:
    rounded_latitude = round(latitude, 6)
    rounded_longitude = round(longitude, 6)
    if not (-90.0 <= rounded_latitude <= 90.0) or not (-180.0 <= rounded_longitude <= 180.0):
        raise point_invalid_coordinates()
    if rounded_latitude == 0.0 and rounded_longitude == 0.0:
        raise point_invalid_coordinates()
    return rounded_latitude, rounded_longitude


def _constraint_name(exc: IntegrityError) -> str | None:
    orig = exc.orig
    for value in (
        getattr(orig, "constraint_name", None),
        getattr(getattr(orig, "diag", None), "constraint_name", None),
    ):
        if value:
            return str(value)

    message = str(orig)
    for name in _COORDINATE_CONSTRAINTS | _INVALID_COORDINATE_CONSTRAINTS | _NAME_CONSTRAINTS | _CODE_CONSTRAINTS:
        if name in message:
            return name
    return None


def _point_problem_from_integrity(exc: IntegrityError, *, code: str | None = None):
    constraint = _constraint_name(exc)
    if constraint in _COORDINATE_CONSTRAINTS:
        return point_coordinate_conflict()
    if constraint in _INVALID_COORDINATE_CONSTRAINTS:
        return point_invalid_coordinates()
    if constraint in _NAME_CONSTRAINTS:
        return point_name_conflict()
    if constraint in _CODE_CONSTRAINTS:
        if constraint == "chk_location_points_code_format":
            return request_validation_error(
                [{"field": "body.code", "message": "Point code must match ^[A-Z0-9_]{2,32}$.", "type": "value_error"}]
            )
        return point_code_conflict(code or "")
    return None


async def _raise_name_conflict_if_needed(
    session: AsyncSession,
    *,
    normalized_name_tr: str,
    normalized_name_en: str,
    exclude_location_id: str | None = None,
) -> None:
    stmt = select(LocationPoint).where(
        or_(
            LocationPoint.normalized_name_tr == normalized_name_tr,
            LocationPoint.normalized_name_en == normalized_name_en,
        )
    )
    if exclude_location_id is not None:
        stmt = stmt.where(LocationPoint.location_id != exclude_location_id)

    conflict = (await session.execute(stmt)).scalar_one_or_none()
    if conflict is not None:
        raise point_name_conflict(f"Normalized name conflicts with existing point '{conflict.code}'.")


@router.post("", response_model=PointResponse, status_code=201)
async def create_point(
    payload: PointCreate,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(user_auth_dependency)],
) -> PointResponse:
    """Create a canonical Location Point."""
    code = _validate_code(payload.code)
    name_tr = _strip_name(payload.name_tr)
    name_en = _strip_name(payload.name_en)
    latitude_6dp, longitude_6dp = _validate_coordinates(payload.latitude_6dp, payload.longitude_6dp)

    existing = (
        await session.execute(select(LocationPoint).where(func.lower(LocationPoint.code) == func.lower(code)))
    ).scalar_one_or_none()
    if existing is not None:
        raise point_code_conflict(code)

    normalized_tr = normalize_tr(name_tr)
    normalized_en = normalize_en(name_en)
    await _raise_name_conflict_if_needed(
        session,
        normalized_name_tr=normalized_tr,
        normalized_name_en=normalized_en,
    )

    point = LocationPoint(
        location_id=str(ULID()),
        code=code,
        name_tr=name_tr,
        name_en=name_en,
        normalized_name_tr=normalized_tr,
        normalized_name_en=normalized_en,
        latitude_6dp=latitude_6dp,
        longitude_6dp=longitude_6dp,
        is_active=payload.is_active,
    )
    session.add(point)
    await session.flush()

    # High-fidelity audit & outbox
    new_snapshot = serialize_point(point)
    await _write_audit(
        session,
        target_type="POINT",
        target_id=str(point.location_id),
        action_type="CREATE",
        actor_id=auth.actor_id if "auth" in locals() else "SYSTEM",
        actor_role=auth.actor_type if "auth" in locals() else "ADMIN",
        new_snapshot=new_snapshot,
    )
    await _write_outbox(
        session,
        event_name="location.point.created.v1",
        payload={
            "location_id": str(point.location_id),
            "code": point.code,
            "occurred_at_utc": new_snapshot["created_at_utc"],
        },
    )

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        problem = _point_problem_from_integrity(exc, code=code)
        if problem is not None:
            raise problem
        raise

    await session.refresh(point)
    set_etag(response, point.row_version)
    return point


@router.get("/{location_id}", response_model=PointResponse)
async def get_point(
    location_id: str,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PointResponse:
    """Retrieve a Location Point by ID."""
    point = (
        await session.execute(select(LocationPoint).where(LocationPoint.location_id == location_id))
    ).scalar_one_or_none()
    if point is None:
        raise point_not_found(str(location_id))
    set_etag(response, point.row_version)
    return point


@router.get("", response_model=PointListResponse)
async def list_points(
    session: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int | None, Query(ge=1, le=100)] = None,
    limit: Annotated[int | None, Query(ge=1, le=100, description="Deprecated alias for per_page.")] = None,
    is_active: Annotated[bool | None, Query()] = None,
    search: Annotated[str | None, Query(min_length=2)] = None,
    sort: Annotated[str | None, Query()] = None,
) -> dict[str, object]:
    """List Location Points with optional filtering and pagination."""
    pagination = resolve_pagination(page=page, per_page=per_page, limit=limit)
    sort_contract = resolve_sort(sort=sort, allowed=_ALLOWED_SORTS, default=_DEFAULT_SORT)
    order_by = build_order_by(
        sort_contract,
        {
            "updated_at_utc": LocationPoint.updated_at_utc,
            "created_at_utc": LocationPoint.created_at_utc,
            "code": LocationPoint.code,
        },
    )

    stmt = select(LocationPoint)

    if is_active is not None:
        stmt = stmt.where(LocationPoint.is_active.is_(is_active))

    if search:
        normalized_search_tr = normalize_tr(search)
        normalized_search_en = normalize_en(search)
        stmt = stmt.where(
            or_(
                LocationPoint.code.ilike(f"%{search}%"),
                LocationPoint.normalized_name_tr.ilike(f"%{normalized_search_tr}%"),
                LocationPoint.normalized_name_en.ilike(f"%{normalized_search_en}%"),
            )
        )

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total_items = (await session.execute(count_stmt)).scalar() or 0
    total_pages = (total_items + pagination.per_page - 1) // pagination.per_page if total_items else 0

    items = (
        (
            await session.execute(
                stmt.order_by(order_by, LocationPoint.location_id.desc())
                .offset(pagination.offset)
                .limit(pagination.per_page)
            )
        )
        .scalars()
        .all()
    )

    return {
        "data": list(items),
        "meta": PaginationMeta(
            page=pagination.page,
            per_page=pagination.per_page,
            total_items=total_items,
            total_pages=total_pages,
            sort=sort_contract.token,
        ).model_dump(),
    }


@router.patch("/{location_id}", response_model=PointResponse)
async def update_point(
    location_id: str,
    payload: PointUpdate,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(user_auth_dependency)],
) -> PointResponse:
    """Partial update of a Location Point."""
    point = (
        await session.execute(select(LocationPoint).where(LocationPoint.location_id == location_id))
    ).scalar_one_or_none()
    if point is None:
        raise point_not_found(str(location_id))

    check_version_match(request, point.row_version)
    update_data = payload.model_dump(exclude_unset=True)

    immutable_fields = {"latitude_6dp", "longitude_6dp", "code"}
    if immutable_fields.intersection(update_data):
        raise point_immutable_field_modification()

    next_name_tr = point.name_tr
    next_name_en = point.name_en

    if "name_tr" in update_data:
        next_name_tr = _strip_name(update_data["name_tr"])
    if "name_en" in update_data:
        next_name_en = _strip_name(update_data["name_en"])

    normalized_tr = normalize_tr(next_name_tr)
    normalized_en = normalize_en(next_name_en)
    if normalized_tr != point.normalized_name_tr or normalized_en != point.normalized_name_en:
        await _raise_name_conflict_if_needed(
            session,
            normalized_name_tr=normalized_tr,
            normalized_name_en=normalized_en,
            exclude_location_id=location_id,
        )

    if "is_active" in update_data and update_data["is_active"] is False and point.is_active is True:
        blocking_pair = (
            await session.execute(
                select(RoutePair).where(
                    or_(
                        RoutePair.origin_location_id == location_id,
                        RoutePair.destination_location_id == location_id,
                    ),
                    RoutePair.pair_status.in_([PairStatus.ACTIVE, PairStatus.DRAFT]),
                )
            )
        ).scalar_one_or_none()
        if blocking_pair is not None:
            raise point_in_use_by_active_pair()

    changed = False
    if next_name_tr != point.name_tr:
        point.name_tr = next_name_tr
        point.normalized_name_tr = normalized_tr
        changed = True
    if next_name_en != point.name_en:
        point.name_en = next_name_en
        point.normalized_name_en = normalized_en
        changed = True
    if "is_active" in update_data and update_data["is_active"] != point.is_active:
        point.is_active = update_data["is_active"]
        changed = True

    if changed:
        old_snapshot = serialize_point(point)
        point.row_version += 1
        await session.flush()
        new_snapshot = serialize_point(point)

        # High-fidelity audit & outbox
        await _write_audit(
            session,
            target_type="POINT",
            target_id=str(point.location_id),
            action_type="UPDATE",
            actor_id=auth.actor_id if "auth" in locals() else "SYSTEM",
            actor_role=auth.actor_type if "auth" in locals() else "ADMIN",
            old_snapshot=old_snapshot,
            new_snapshot=new_snapshot,
            request_id=request.headers.get("X-Request-ID"),
        )
        await _write_outbox(
            session,
            event_name="location.point.updated.v1",
            payload={
                "location_id": str(point.location_id),
                "code": point.code,
                "occurred_at_utc": new_snapshot["updated_at_utc"],
            },
        )

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        problem = _point_problem_from_integrity(exc, code=point.code)
        if problem is not None:
            raise problem
        raise

    await session.refresh(point)
    set_etag(response, point.row_version)
    return point
