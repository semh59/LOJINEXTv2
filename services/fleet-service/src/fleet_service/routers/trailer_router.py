"""Trailer API router — 12 endpoints (Phase E — mirrors vehicle + spec).

All endpoints produce application/json, errors produce application/problem+json.
"""

from __future__ import annotations

import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Response

from fleet_service.auth import AuthContext, admin_auth, super_admin_auth
from fleet_service.database import AsyncSessionDep
from fleet_service.schemas.requests import (
    HardDeleteRequest,
    LifecycleActionRequest,
    TrailerCreateRequest,
    TrailerPatchRequest,
    TrailerSpecVersionRequest,
)
from fleet_service.schemas.responses import HardDeleteResponse, TrailerDetailResponse, TrailerSpecResponse
from fleet_service.services import trailer_service

router = APIRouter(prefix="/api/v1/trailers", tags=["trailers"])


# --- POST /api/v1/trailers ---


@router.post("", status_code=201)
async def create_trailer(
    body: TrailerCreateRequest,
    session: AsyncSessionDep,
    auth: Annotated[AuthContext, Depends(admin_auth)],
    response: Response,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
) -> TrailerDetailResponse:
    """Create a new trailer (idempotent)."""
    result, etag, status_code = await trailer_service.create_trailer(
        session,
        body,
        auth,
        idempotency_key=idempotency_key,
        request_id=x_request_id,
        correlation_id=x_correlation_id,
    )
    await session.commit()
    response.status_code = status_code
    response.headers["ETag"] = etag
    return result


# --- GET /api/v1/trailers ---


@router.get("")
async def list_trailers(
    session: AsyncSessionDep,
    _auth: Annotated[AuthContext, Depends(admin_auth)],
    status: str | None = Query(None),
    ownership_type: str | None = Query(None),
    q: str | None = Query(None, description="Search plate/asset_code"),
    sort: str = Query("updated_at_desc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    include_inactive: bool = Query(False),
    include_soft_deleted: bool = Query(False),
) -> Any:
    """List trailers with filters, sort, pagination."""
    return await trailer_service.list_trailers(
        session,
        status=status,
        ownership_type=ownership_type,
        q=q,
        sort=sort,
        page=page,
        per_page=per_page,
        include_inactive=include_inactive,
        include_soft_deleted=include_soft_deleted,
    )


# --- GET /api/v1/trailers/{trailer_id} ---


@router.get("/{trailer_id}")
async def get_trailer(
    trailer_id: str,
    session: AsyncSessionDep,
    _auth: Annotated[AuthContext, Depends(admin_auth)],
    response: Response,
) -> TrailerDetailResponse:
    """Get trailer detail with current spec summary."""
    result, etag = await trailer_service.get_trailer_detail(session, trailer_id)
    response.headers["ETag"] = etag
    return result


# --- PATCH /api/v1/trailers/{trailer_id} ---


@router.patch("/{trailer_id}")
async def patch_trailer(
    trailer_id: str,
    body: TrailerPatchRequest,
    session: AsyncSessionDep,
    auth: Annotated[AuthContext, Depends(admin_auth)],
    response: Response,
    if_match: str | None = Header(None, alias="If-Match"),
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
) -> TrailerDetailResponse:
    """Update trailer master fields (optimistic concurrency)."""
    result, etag = await trailer_service.patch_trailer(
        session,
        trailer_id,
        body,
        auth,
        if_match=if_match,
        request_id=x_request_id,
        correlation_id=x_correlation_id,
    )
    await session.commit()
    response.headers["ETag"] = etag
    return result


# --- POST /api/v1/trailers/{trailer_id}/deactivate ---


@router.post("/{trailer_id}/deactivate")
async def deactivate_trailer(
    trailer_id: str,
    body: LifecycleActionRequest,
    session: AsyncSessionDep,
    auth: Annotated[AuthContext, Depends(admin_auth)],
    response: Response,
    if_match: str | None = Header(None, alias="If-Match"),
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
) -> TrailerDetailResponse:
    """ACTIVE → INACTIVE."""
    result, etag = await trailer_service.deactivate_trailer(
        session,
        trailer_id,
        body.reason,
        auth,
        if_match=if_match,
        request_id=x_request_id,
        correlation_id=x_correlation_id,
    )
    await session.commit()
    response.headers["ETag"] = etag
    return result


# --- POST /api/v1/trailers/{trailer_id}/reactivate ---


@router.post("/{trailer_id}/reactivate")
async def reactivate_trailer(
    trailer_id: str,
    body: LifecycleActionRequest,
    session: AsyncSessionDep,
    auth: Annotated[AuthContext, Depends(admin_auth)],
    response: Response,
    if_match: str | None = Header(None, alias="If-Match"),
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
) -> TrailerDetailResponse:
    """INACTIVE → ACTIVE."""
    result, etag = await trailer_service.reactivate_trailer(
        session,
        trailer_id,
        body.reason,
        auth,
        if_match=if_match,
        request_id=x_request_id,
        correlation_id=x_correlation_id,
    )
    await session.commit()
    response.headers["ETag"] = etag
    return result


# --- POST /api/v1/trailers/{trailer_id}/soft-delete ---


@router.post("/{trailer_id}/soft-delete")
async def soft_delete_trailer(
    trailer_id: str,
    body: LifecycleActionRequest,
    session: AsyncSessionDep,
    auth: Annotated[AuthContext, Depends(admin_auth)],
    response: Response,
    if_match: str | None = Header(None, alias="If-Match"),
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
) -> TrailerDetailResponse:
    """Set soft_deleted_at_utc fields."""
    result, etag = await trailer_service.soft_delete_trailer(
        session,
        trailer_id,
        body.reason,
        auth,
        if_match=if_match,
        request_id=x_request_id,
        correlation_id=x_correlation_id,
    )
    await session.commit()
    response.headers["ETag"] = etag
    return result


# --- POST /api/v1/trailers/{trailer_id}/hard-delete ---


@router.post("/{trailer_id}/hard-delete")
async def hard_delete_trailer(
    trailer_id: str,
    body: HardDeleteRequest,
    session: AsyncSessionDep,
    auth: Annotated[AuthContext, Depends(super_admin_auth)],
    if_match: str | None = Header(None, alias="If-Match"),
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
) -> HardDeleteResponse:
    """Hard-delete (SUPER_ADMIN only, 4-stage pipeline)."""
    result = await trailer_service.hard_delete_trailer(
        session,
        trailer_id,
        body.reason,
        auth,
        if_match=if_match,
        request_id=x_request_id,
        correlation_id=x_correlation_id,
    )
    await session.commit()
    return HardDeleteResponse(**result)


# --- GET /api/v1/trailers/{trailer_id}/timeline ---


@router.get("/{trailer_id}/timeline")
async def get_trailer_timeline(
    trailer_id: str,
    session: AsyncSessionDep,
    _auth: Annotated[AuthContext, Depends(admin_auth)],
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
) -> Any:
    """Get trailer timeline events."""
    return await trailer_service.get_trailer_timeline(session, trailer_id, page=page, per_page=per_page)


# --- POST /api/v1/trailers/{trailer_id}/spec-versions ---


@router.post("/{trailer_id}/spec-versions", status_code=201)
async def create_trailer_spec_version(
    trailer_id: str,
    body: TrailerSpecVersionRequest,
    session: AsyncSessionDep,
    auth: Annotated[AuthContext, Depends(admin_auth)],
    response: Response,
    if_match: str | None = Header(None, alias="If-Match"),
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
) -> TrailerSpecResponse:
    """Create a new spec version for a trailer (spec ETag required)."""
    result, etag, status_code = await trailer_service.create_trailer_spec_version(
        session,
        trailer_id,
        body,
        auth,
        if_match=if_match,
        request_id=x_request_id,
        correlation_id=x_correlation_id,
    )
    await session.commit()
    response.status_code = status_code
    response.headers["ETag"] = etag
    return result


# --- GET /api/v1/trailers/{trailer_id}/spec/current ---


@router.get("/{trailer_id}/spec/current")
async def get_trailer_spec_current(
    trailer_id: str,
    session: AsyncSessionDep,
    _auth: Annotated[AuthContext, Depends(admin_auth)],
    response: Response,
) -> TrailerSpecResponse:
    """Get the current spec version for a trailer."""
    result, etag = await trailer_service.get_current_spec(session, trailer_id)
    response.headers["ETag"] = etag
    return result


# --- GET /api/v1/trailers/{trailer_id}/spec/as-of ---


@router.get("/{trailer_id}/spec/as-of")
async def get_trailer_spec_as_of(
    trailer_id: str,
    session: AsyncSessionDep,
    _auth: Annotated[AuthContext, Depends(admin_auth)],
    at: datetime.datetime = Query(..., description="ISO 8601 timestamp to query spec at"),
) -> TrailerSpecResponse:
    """Get the spec version effective at a given timestamp."""
    return await trailer_service.get_spec_as_of(session, trailer_id, at)
