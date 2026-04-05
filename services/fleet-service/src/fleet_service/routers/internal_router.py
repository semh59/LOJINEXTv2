"""Internal API router — 8 endpoints for service-to-service calls (Phase F).

All endpoints require SERVICE JWT auth and live under /internal/v1/.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from fleet_service.auth import AuthContext, trip_service_auth
from fleet_service.database import AsyncSessionDep
from fleet_service.schemas.requests import (
    FuelMetadataResolveRequest,
    TripCompatRequest,
    ValidateBulkRequest,
)
from fleet_service.schemas.responses import (
    CursorResponse,
    FuelMetadataResolveResponse,
    ValidateBulkItemResponse,
    ValidateResponse,
)
from fleet_service.services import internal_service

router = APIRouter(prefix="/internal/v1", tags=["internal"])


# --- GET /internal/v1/vehicles/{vehicle_id}/validate ---


@router.get("/vehicles/{vehicle_id}/validate")
async def validate_vehicle(
    vehicle_id: str,
    session: AsyncSessionDep,
    _auth: Annotated[AuthContext, Depends(trip_service_auth)],
) -> ValidateResponse:
    """Validate a vehicle — always 200."""
    return await internal_service.validate_single(session, "VEHICLE", vehicle_id)


# --- GET /internal/v1/trailers/{trailer_id}/validate ---


@router.get("/trailers/{trailer_id}/validate")
async def validate_trailer(
    trailer_id: str,
    session: AsyncSessionDep,
    _auth: Annotated[AuthContext, Depends(trip_service_auth)],
) -> ValidateResponse:
    """Validate a trailer — always 200."""
    return await internal_service.validate_single(session, "TRAILER", trailer_id)


# --- POST /internal/v1/assets/validate-bulk ---


@router.post("/assets/validate-bulk")
async def validate_bulk(
    body: ValidateBulkRequest,
    session: AsyncSessionDep,
    _auth: Annotated[AuthContext, Depends(trip_service_auth)],
) -> list[ValidateBulkItemResponse]:
    """Validate multiple vehicles and trailers in one call."""
    return await internal_service.validate_bulk(session, body.vehicle_ids, body.trailer_ids)


# --- POST /internal/v1/trip-references/validate ---


@router.post("/trip-references/validate")
async def validate_trip_compat(
    body: TripCompatRequest,
    session: AsyncSessionDep,
    _auth: Annotated[AuthContext, Depends(trip_service_auth)],
) -> Any:
    """Validate driver + vehicle + optional trailer for trip creation."""
    return await internal_service.validate_trip_compat_contract(
        session,
        body.driver_id,
        body.vehicle_id,
        body.trailer_id,
    )


# --- GET /internal/v1/selectable/vehicles ---


@router.get("/selectable/vehicles")
async def list_selectable_vehicles(
    session: AsyncSessionDep,
    _auth: Annotated[AuthContext, Depends(trip_service_auth)],
    q: str | None = Query(None, description="Search plate/asset_code"),
    cursor: str | None = Query(None, description="Cursor for next page"),
    limit: int = Query(50, ge=1, le=200),
) -> CursorResponse:
    """Get selectable vehicles, cursor-paginated."""
    return await internal_service.list_selectable_vehicles(session, q=q, cursor=cursor, limit=limit)


# --- GET /internal/v1/selectable/trailers ---


@router.get("/selectable/trailers")
async def list_selectable_trailers(
    session: AsyncSessionDep,
    _auth: Annotated[AuthContext, Depends(trip_service_auth)],
    q: str | None = Query(None, description="Search plate/asset_code"),
    cursor: str | None = Query(None, description="Cursor for next page"),
    limit: int = Query(50, ge=1, le=200),
) -> CursorResponse:
    """Get selectable trailers, cursor-paginated."""
    return await internal_service.list_selectable_trailers(session, q=q, cursor=cursor, limit=limit)


# --- POST /internal/v1/assets/fuel-metadata/resolve ---


@router.post("/assets/fuel-metadata/resolve")
async def resolve_fuel_metadata(
    body: FuelMetadataResolveRequest,
    session: AsyncSessionDep,
    _auth: Annotated[AuthContext, Depends(trip_service_auth)],
) -> FuelMetadataResolveResponse:
    """Resolve fuel metadata for vehicle + optional trailer."""
    return await internal_service.resolve_fuel_metadata(
        session,
        body.vehicle_id,
        body.trailer_id,
        body.at,
    )
