"""Tests for public route-version detail and geometry endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from location_service.enums import DirectionCode, PairStatus, ProcessingStatus, SpeedBand, SpeedLimitState, UrbanClass
from location_service.models import LocationPoint, Route, RoutePair, RouteSegment, RouteVersion


async def _seed_route_version(test_session: AsyncSession) -> tuple[Route, RouteVersion]:
    origin = LocationPoint(
        location_id=uuid4(),
        code="RV_O",
        name_tr="Route Version Origin",
        name_en="Route Version Origin",
        normalized_name_tr="ROUTE VERSION ORIGIN",
        normalized_name_en="ROUTE VERSION ORIGIN",
        latitude_6dp=41.0,
        longitude_6dp=29.0,
        is_active=True,
    )
    destination = LocationPoint(
        location_id=uuid4(),
        code="RV_D",
        name_tr="Route Version Destination",
        name_en="Route Version Destination",
        normalized_name_tr="ROUTE VERSION DESTINATION",
        normalized_name_en="ROUTE VERSION DESTINATION",
        latitude_6dp=40.5,
        longitude_6dp=28.5,
        is_active=True,
    )
    pair = RoutePair(
        route_pair_id=uuid4(),
        pair_code="RP_BBBBBBBBBBBBBBBBBBBBBBBBBB",
        origin_location_id=origin.location_id,
        destination_location_id=destination.location_id,
        profile_code="TIR",
        pair_status=PairStatus.ACTIVE,
        row_version=3,
    )
    test_session.add_all([origin, destination, pair])
    await test_session.flush()
    route = Route(
        route_id=uuid4(),
        route_pair_id=pair.route_pair_id,
        route_code="ROUTE_DETAIL_001",
        direction=DirectionCode.FORWARD,
        created_by="test",
    )
    test_session.add(route)
    await test_session.flush()
    version = RouteVersion(
        route_id=route.route_id,
        version_no=2,
        processing_run_id=None,
        processing_status=ProcessingStatus.ACTIVE,
        total_distance_m=1234.5,
        total_duration_s=987,
        total_ascent_m=45.5,
        total_descent_m=40.2,
        avg_grade_pct=1.2,
        max_grade_pct=6.7,
        steepest_downhill_pct=-4.5,
        known_speed_limit_ratio=0.92,
        segment_count=2,
        validation_result="PASS",
        distance_validation_delta_pct=0.5,
        duration_validation_delta_pct=1.0,
        endpoint_validation_delta_m=4.2,
        field_origin_matrix_json={"source": "mapbox"},
        field_origin_matrix_hash="hash",
        road_type_distribution_json={"PRIMARY": 0.6},
        speed_limit_distribution_json={"80_PLUS": 0.7},
        urban_distribution_json={"URBAN": 0.3},
        warnings_json=["minor warning"],
        refresh_reason="manual",
        processing_algorithm_version="algo-v1",
        created_at_utc=datetime(2026, 3, 28, 10, 0, tzinfo=UTC),
        activated_at_utc=datetime(2026, 3, 28, 10, 5, tzinfo=UTC),
    )
    segments = [
        RouteSegment(
            route_id=route.route_id,
            version_no=version.version_no,
            segment_no=1,
            start_latitude_6dp=41.0,
            start_longitude_6dp=29.0,
            end_latitude_6dp=40.8,
            end_longitude_6dp=28.8,
            distance_m=600.0,
            start_elevation_m=100.0,
            end_elevation_m=110.0,
            grade_pct=1.0,
            grade_class="FLAT",
            road_class="PRIMARY",
            urban_class=UrbanClass.URBAN,
            speed_limit_kph=80,
            speed_limit_state=SpeedLimitState.KNOWN,
            speed_band=SpeedBand.BAND_80_PLUS,
            tunnel_flag=False,
        ),
        RouteSegment(
            route_id=route.route_id,
            version_no=version.version_no,
            segment_no=2,
            start_latitude_6dp=40.8,
            start_longitude_6dp=28.8,
            end_latitude_6dp=40.5,
            end_longitude_6dp=28.5,
            distance_m=634.5,
            start_elevation_m=110.0,
            end_elevation_m=90.0,
            grade_pct=-2.0,
            grade_class="DOWNHILL_MODERATE",
            road_class="PRIMARY",
            urban_class=UrbanClass.NON_URBAN,
            speed_limit_kph=90,
            speed_limit_state=SpeedLimitState.KNOWN,
            speed_band=SpeedBand.BAND_80_PLUS,
            tunnel_flag=False,
        ),
    ]
    test_session.add(version)
    await test_session.flush()
    test_session.add_all(segments)
    await test_session.commit()
    return route, version


@pytest.mark.asyncio
async def test_get_route_version_detail(client: AsyncClient, test_session: AsyncSession) -> None:
    route, version = await _seed_route_version(test_session)

    response = await client.get(f"/v1/routes/{route.route_id}/versions/{version.version_no}")
    assert response.status_code == 200
    body = response.json()
    assert body["route_id"] == str(route.route_id)
    assert body["route_code"] == route.route_code
    assert body["pair_code"] == "RP_BBBBBBBBBBBBBBBBBBBBBBBBBB"
    assert body["direction"] == "FORWARD"
    assert body["processing_status"] == "ACTIVE"
    assert body["validation_result"] == "PASS"
    assert body["road_type_distribution_json"] == {"PRIMARY": 0.6}
    assert body["warnings_json"] == ["minor warning"]


@pytest.mark.asyncio
async def test_get_route_version_geometry_returns_ordered_coordinates(
    client: AsyncClient,
    test_session: AsyncSession,
) -> None:
    route, version = await _seed_route_version(test_session)

    response = await client.get(f"/v1/routes/{route.route_id}/versions/{version.version_no}/geometry")
    assert response.status_code == 200
    body = response.json()
    assert body["route_id"] == str(route.route_id)
    assert body["version_no"] == version.version_no
    assert body["coordinate_count"] == 3
    assert body["coordinates"] == [[29.0, 41.0], [28.8, 40.8], [28.5, 40.5]]


@pytest.mark.asyncio
async def test_missing_route_version_returns_not_found(client: AsyncClient) -> None:
    response = await client.get(f"/v1/routes/{uuid4()}/versions/1")
    assert response.status_code == 404
    assert response.json()["code"] == "LOCATION_ROUTE_VERSION_NOT_FOUND"

    geometry = await client.get(f"/v1/routes/{uuid4()}/versions/1/geometry")
    assert geometry.status_code == 404
    assert geometry.json()["code"] == "LOCATION_ROUTE_VERSION_NOT_FOUND"
