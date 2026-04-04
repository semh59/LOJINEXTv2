"""Vehicle spec version API router — 3 endpoints (Phase D).

All endpoints produce application/json, errors produce application/problem+json.
"""

from __future__ import annotations

import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response

from fleet_service.auth import AuthContext, admin_auth
from fleet_service.database import AsyncSessionDep
from fleet_service.schemas.requests import VehicleSpecVersionRequest
from fleet_service.schemas.responses import VehicleSpecResponse
from fleet_service.services import vehicle_spec_service

router = APIRouter(prefix="/api/v1/vehicles", tags=["vehicle-specs"])


# --- POST /api/v1/vehicles/{vehicle_id}/spec-versions ---


@router.post("/{vehicle_id}/spec-versions", status_code=201)
async def create_vehicle_spec_version(
    vehicle_id: str,
    body: VehicleSpecVersionRequest,
    session: AsyncSessionDep,
    auth: Annotated[AuthContext, Depends(admin_auth)],
    response: Response,
    if_match: str | None = Header(None, alias="If-Match"),
    x_request_id: str | None = Header(None, alias="X-Request-ID"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
) -> VehicleSpecResponse:
    """Create a new spec version for a vehicle (spec ETag required)."""
    result, etag, status_code = await vehicle_spec_service.create_vehicle_spec_version(
        session,
        vehicle_id,
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


# --- GET /api/v1/vehicles/{vehicle_id}/spec/current ---


@router.get("/{vehicle_id}/spec/current")
async def get_vehicle_spec_current(
    vehicle_id: str,
    session: AsyncSessionDep,
    _auth: Annotated[AuthContext, Depends(admin_auth)],
    response: Response,
) -> VehicleSpecResponse:
    """Get the current spec version for a vehicle."""
    result, etag = await vehicle_spec_service.get_current_spec(session, vehicle_id)
    response.headers["ETag"] = etag
    return result


# --- GET /api/v1/vehicles/{vehicle_id}/spec/as-of ---


@router.get("/{vehicle_id}/spec/as-of")
async def get_vehicle_spec_as_of(
    vehicle_id: str,
    session: AsyncSessionDep,
    _auth: Annotated[AuthContext, Depends(admin_auth)],
    at: datetime.datetime = Query(..., description="ISO 8601 timestamp to query spec at"),
) -> VehicleSpecResponse:
    """Get the spec version effective at a given timestamp."""
    return await vehicle_spec_service.get_spec_as_of(session, vehicle_id, at)
