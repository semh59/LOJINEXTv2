"""Frontend-facing public route detail and geometry endpoints."""

from __future__ import annotations

import json
from typing import cast

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..errors import internal_error, route_version_not_found
from ..models import Route, RoutePair, RouteSegment, RouteVersion
from ..schemas import RouteGeometryResponse, RouteVersionDetailResponse

router = APIRouter(tags=["routes"])


async def _get_route_version_row(
    session: AsyncSession,
    *,
    route_id: str,
    version_no: int,
) -> tuple[RouteVersion, Route, RoutePair]:
    row = (
        await session.execute(
            select(RouteVersion, Route, RoutePair)
            .join(Route, Route.route_id == RouteVersion.route_id)
            .join(RoutePair, RoutePair.route_pair_id == Route.route_pair_id)
            .where(RouteVersion.route_id == route_id, RouteVersion.version_no == version_no)
        )
    ).one_or_none()
    if row is None:
        raise route_version_not_found()
    return cast(tuple[RouteVersion, Route, RoutePair], row)


@router.get("/api/v1/routes/{route_id}/versions/{version_no}", response_model=RouteVersionDetailResponse)
async def get_route_version_detail(
    route_id: str,
    version_no: int,
    session: AsyncSession = Depends(get_db),
) -> RouteVersionDetailResponse:
    """Return frontend-facing route version detail."""
    version, route, pair = await _get_route_version_row(session, route_id=route_id, version_no=version_no)

    # Parse JSON fields safely for Pydantic
    try:
        road_type = json.loads(version.road_type_distribution_json)
        speed_dist = json.loads(version.speed_limit_distribution_json)
        urban_dist = json.loads(version.urban_distribution_json)
        warnings = json.loads(version.warnings_json)
    except (TypeError, json.JSONDecodeError):
        # Fallback for corrupted or empty data
        road_type = {}
        speed_dist = {}
        urban_dist = {}
        warnings = []

    return RouteVersionDetailResponse(
        route_id=route.route_id,
        route_code=route.route_code,
        pair_id=pair.route_pair_id,
        pair_code=pair.pair_code,
        direction=route.direction,
        version_no=version.version_no,
        processing_status=version.processing_status,
        total_distance_m=version.total_distance_m,
        total_duration_s=version.total_duration_s,
        total_ascent_m=version.total_ascent_m,
        total_descent_m=version.total_descent_m,
        avg_grade_pct=version.avg_grade_pct,
        max_grade_pct=version.max_grade_pct,
        steepest_downhill_pct=version.steepest_downhill_pct,
        known_speed_limit_ratio=version.known_speed_limit_ratio,
        segment_count=version.segment_count,
        validation_result=version.validation_result,
        distance_validation_delta_pct=version.distance_validation_delta_pct,
        duration_validation_delta_pct=version.duration_validation_delta_pct,
        endpoint_validation_delta_m=version.endpoint_validation_delta_m,
        road_type_distribution_json=road_type,
        speed_limit_distribution_json=speed_dist,
        urban_distribution_json=urban_dist,
        warnings_json=warnings,
        refresh_reason=version.refresh_reason,
        processing_algorithm_version=version.processing_algorithm_version,
        created_at_utc=version.created_at_utc,
        activated_at_utc=version.activated_at_utc,
    )


@router.get("/api/v1/routes/{route_id}/versions/{version_no}/geometry", response_model=RouteGeometryResponse)
async def get_route_version_geometry(
    route_id: str,
    version_no: int,
    session: AsyncSession = Depends(get_db),
) -> RouteGeometryResponse:
    """Return reconstructed 2D geometry for a route version."""
    version, route, _pair = await _get_route_version_row(session, route_id=route_id, version_no=version_no)
    segments = (
        (
            await session.execute(
                select(RouteSegment)
                .where(RouteSegment.route_id == route_id, RouteSegment.version_no == version_no)
                .order_by(RouteSegment.segment_no.asc())
            )
        )
        .scalars()
        .all()
    )
    if not segments:
        raise internal_error("Route version geometry is incomplete.")

    # Validate that segment_no is contiguous 1..N before reconstructing coordinates.
    # A gap would silently produce incorrect geometry.
    expected_nos = list(range(1, len(segments) + 1))
    actual_nos = [s.segment_no for s in segments]
    if actual_nos != expected_nos:
        raise internal_error("Route version geometry is corrupt: non-contiguous segment numbers.")

    coordinates: list[list[float]] = [[float(segments[0].start_longitude_6dp), float(segments[0].start_latitude_6dp)]]
    coordinates.extend([float(segment.end_longitude_6dp), float(segment.end_latitude_6dp)] for segment in segments)

    return RouteGeometryResponse(
        route_id=route.route_id,
        version_no=version.version_no,
        direction=route.direction,
        coordinate_count=len(coordinates),
        coordinates=coordinates,
    )
