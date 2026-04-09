"""Vehicle API router — 9 public endpoints (Section 9).

All endpoints produce application/json, errors produce application/problem+json.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Response

from fleet_service.auth import AuthContext, admin_auth, super_admin_auth
from fleet_service.clients import trip_client
from fleet_service.database import AsyncSessionDep
from fleet_service.schemas.requests import (
    HardDeleteRequest,
    LifecycleActionRequest,
    VehicleCreateRequest,
    VehiclePatchRequest,
)
from fleet_service.schemas.responses import HardDeleteResponse, VehicleDetailResponse
from fleet_service.services import vehicle_service

router = APIRouter(prefix="/api/v1/vehicles", tags=["vehicles"])


# --- POST /api/v1/vehicles ---


@router.post("", status_code=201)
async def create_vehicle(
    body: VehicleCreateRequest,
    session: AsyncSessionDep,
    auth: Annotated[AuthContext, Depends(admin_auth)],
    response: Response,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
) -> VehicleDetailResponse:
    """Create a new vehicle (idempotent)."""
    result, etag, status_code, spec_etag = await vehicle_service.create_vehicle(
        session,
        body,
        auth,
        idempotency_key=idempotency_key,
        request_id=x_request_id,
        correlation_id=x_correlation_id,
    )
    response.status_code = status_code
    response.headers["ETag"] = etag
    if spec_etag is not None:
        response.headers["X-Spec-ETag"] = spec_etag
    return result


# --- GET /api/v1/vehicles ---


@router.get("")
async def list_vehicles(
    session: AsyncSessionDep,
    _auth: Annotated[AuthContext, Depends(admin_auth)],
    status: str | None = Query(None),
    ownership_type: str | None = Query(None),
    q: str | None = Query(None, description="Search plate/asset_code"),
    sort: str = Query("updated_at_desc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    include_inactive: bool = Query(False, description="Also show INACTIVE vehicles"),
    include_soft_deleted: bool = Query(False, description="Also show soft-deleted vehicles"),
) -> Any:
    """List vehicles with filters, sort, pagination."""
    return await vehicle_service.list_vehicles(
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


# --- GET /api/v1/vehicles/{vehicle_id} ---


@router.get("/{vehicle_id}")
async def get_vehicle(
    vehicle_id: str,
    session: AsyncSessionDep,
    _auth: Annotated[AuthContext, Depends(admin_auth)],
    response: Response,
) -> VehicleDetailResponse:
    """Get vehicle detail with current spec summary."""
    result, etag = await vehicle_service.get_vehicle_detail(session, vehicle_id)
    response.headers["ETag"] = etag
    return result


# --- PATCH /api/v1/vehicles/{vehicle_id} ---


@router.patch("/{vehicle_id}")
async def patch_vehicle(
    vehicle_id: str,
    body: VehiclePatchRequest,
    session: AsyncSessionDep,
    auth: Annotated[AuthContext, Depends(admin_auth)],
    response: Response,
    if_match: str | None = Header(None, alias="If-Match"),
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
) -> VehicleDetailResponse:
    """Update vehicle master fields (optimistic concurrency)."""
    result, etag = await vehicle_service.patch_vehicle(
        session,
        vehicle_id,
        body,
        auth,
        if_match=if_match,
        request_id=x_request_id,
        correlation_id=x_correlation_id,
    )
    response.headers["ETag"] = etag
    return result


# --- POST /api/v1/vehicles/{vehicle_id}/deactivate ---


@router.post("/{vehicle_id}/deactivate")
async def deactivate_vehicle(
    vehicle_id: str,
    body: LifecycleActionRequest,
    session: AsyncSessionDep,
    auth: Annotated[AuthContext, Depends(admin_auth)],
    response: Response,
    if_match: str | None = Header(None, alias="If-Match"),
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
) -> VehicleDetailResponse:
    """ACTIVE → INACTIVE."""
    result, etag = await vehicle_service.deactivate_vehicle(
        session,
        vehicle_id,
        body.reason,
        auth,
        if_match=if_match,
        request_id=x_request_id,
        correlation_id=x_correlation_id,
    )
    response.headers["ETag"] = etag
    return result


# --- POST /api/v1/vehicles/{vehicle_id}/reactivate ---


@router.post("/{vehicle_id}/reactivate")
async def reactivate_vehicle(
    vehicle_id: str,
    body: LifecycleActionRequest,
    session: AsyncSessionDep,
    auth: Annotated[AuthContext, Depends(admin_auth)],
    response: Response,
    if_match: str | None = Header(None, alias="If-Match"),
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
) -> VehicleDetailResponse:
    """INACTIVE → ACTIVE."""
    result, etag = await vehicle_service.reactivate_vehicle(
        session,
        vehicle_id,
        body.reason,
        auth,
        if_match=if_match,
        request_id=x_request_id,
        correlation_id=x_correlation_id,
    )
    response.headers["ETag"] = etag
    return result


# --- POST /api/v1/vehicles/{vehicle_id}/soft-delete ---


@router.post("/{vehicle_id}/soft-delete")
async def soft_delete_vehicle(
    vehicle_id: str,
    body: LifecycleActionRequest,
    session: AsyncSessionDep,
    auth: Annotated[AuthContext, Depends(admin_auth)],
    response: Response,
    if_match: str | None = Header(None, alias="If-Match"),
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
) -> VehicleDetailResponse:
    """Set soft_deleted_at_utc fields."""
    result, etag = await vehicle_service.soft_delete_vehicle(
        session,
        vehicle_id,
        body.reason,
        auth,
        if_match=if_match,
        request_id=x_request_id,
        correlation_id=x_correlation_id,
    )
    response.headers["ETag"] = etag
    return result


# --- POST /api/v1/vehicles/{vehicle_id}/hard-delete ---


@router.post("/{vehicle_id}/hard-delete")
async def hard_delete_vehicle(
    vehicle_id: str,
    body: HardDeleteRequest,
    session: AsyncSessionDep,
    auth: Annotated[AuthContext, Depends(super_admin_auth)],
    if_match: str | None = Header(None, alias="If-Match"),
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
) -> HardDeleteResponse:
    """Hard-delete (SUPER_ADMIN only, 4-stage pipeline)."""
    result = await vehicle_service.hard_delete_vehicle(
        session,
        vehicle_id,
        body.reason,
        auth,
        if_match=if_match,
        request_id=x_request_id,
        correlation_id=x_correlation_id,
        trip_reference_checker=trip_client.check_asset_references,
    )
    return HardDeleteResponse(**result)


# --- GET /api/v1/vehicles/{vehicle_id}/timeline ---


@router.get("/{vehicle_id}/timeline")
async def get_vehicle_timeline(
    vehicle_id: str,
    session: AsyncSessionDep,
    _auth: Annotated[AuthContext, Depends(admin_auth)],
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
) -> Any:
    """Get vehicle timeline events."""
    return await vehicle_service.get_vehicle_timeline(session, vehicle_id, page=page, per_page=per_page)
