"""Tests for the internal route resolve and trip-context contracts."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient

from location_service.domain.normalization import normalize_en, normalize_tr
from location_service.models import LocationPoint, Route, RoutePair, RouteVersion


def _point(
    *,
    code: str,
    name_tr: str,
    name_en: str,
    latitude: float,
    longitude: float,
) -> LocationPoint:
    """Build a location point model for tests."""
    return LocationPoint(
        code=code,
        name_tr=name_tr,
        name_en=name_en,
        normalized_name_tr=normalize_tr(name_tr),
        normalized_name_en=normalize_en(name_en),
        latitude_6dp=latitude,
        longitude_6dp=longitude,
        is_active=True,
    )


def _pair_code() -> str:
    """Generate a pair_code that satisfies the DB constraint."""
    return f"RP_{uuid4().hex[:26].upper()}"


def _route_version(route_id, version_no: int, duration_s: int) -> RouteVersion:  # noqa: ANN001
    """Build a valid active route version row."""
    return RouteVersion(
        route_id=route_id,
        version_no=version_no,
        processing_run_id=None,
        processing_status="ACTIVE",
        total_distance_m=1000,
        total_duration_s=duration_s,
        total_ascent_m=None,
        total_descent_m=None,
        avg_grade_pct=None,
        max_grade_pct=None,
        steepest_downhill_pct=None,
        known_speed_limit_ratio=1,
        segment_count=1,
        validation_result="OK",
        distance_validation_delta_pct=None,
        duration_validation_delta_pct=None,
        endpoint_validation_delta_m=None,
        field_origin_matrix_json={},
        field_origin_matrix_hash="hash",
        road_type_distribution_json={},
        speed_limit_distribution_json={},
        urban_distribution_json={},
        warnings_json=[],
        refresh_reason=None,
        processing_algorithm_version="v1",
    )


@pytest.mark.asyncio
async def test_internal_resolve_returns_forward_active_route(client: AsyncClient, test_session):
    origin = _point(
        code=f"ORG_{uuid4().hex[:8].upper()}",
        name_tr="Ankara",
        name_en="Ankara",
        latitude=39.93,
        longitude=32.85,
    )
    destination = _point(
        code=f"DST_{uuid4().hex[:8].upper()}",
        name_tr="Bursa",
        name_en="Bursa",
        latitude=40.19,
        longitude=29.07,
    )
    test_session.add_all([origin, destination])
    await test_session.flush()

    pair = RoutePair(
        route_pair_id=uuid4(),
        pair_code=_pair_code(),
        origin_location_id=origin.location_id,
        destination_location_id=destination.location_id,
        profile_code="TIR",
        pair_status="ACTIVE",
    )
    test_session.add(pair)
    await test_session.flush()

    forward_route = Route(
        route_id=uuid4(),
        route_pair_id=pair.route_pair_id,
        route_code=f"ROUTE-FWD-{uuid4().hex[:8].upper()}",
        direction="FORWARD",
        created_by="test",
    )
    reverse_route = Route(
        route_id=uuid4(),
        route_pair_id=pair.route_pair_id,
        route_code=f"ROUTE-REV-{uuid4().hex[:8].upper()}",
        direction="REVERSE",
        created_by="test",
    )
    test_session.add_all([forward_route, reverse_route])
    await test_session.flush()

    pair.forward_route_id = forward_route.route_id
    pair.reverse_route_id = reverse_route.route_id
    pair.current_active_forward_version_no = 1
    pair.current_active_reverse_version_no = 1
    test_session.add_all(
        [
            _route_version(forward_route.route_id, 1, 21600),
            _route_version(reverse_route.route_id, 1, 22000),
        ]
    )
    await test_session.commit()

    response = await client.post(
        "/internal/v1/routes/resolve",
        json={
            "origin_name": "Ankara",
            "destination_name": "Bursa",
            "profile_code": "TIR",
            "language_hint": "AUTO",
        },
    )

    assert response.status_code == 200
    assert response.json()["route_id"] == str(forward_route.route_id)
    assert response.json()["pair_id"] == str(pair.route_pair_id)
    assert response.json()["resolution"] == "EXACT_TR"


@pytest.mark.asyncio
async def test_trip_context_returns_forward_and_reverse_durations(client: AsyncClient, test_session):
    origin = _point(
        code=f"ORG_{uuid4().hex[:8].upper()}",
        name_tr="Istanbul",
        name_en="Istanbul",
        latitude=41.01,
        longitude=28.97,
    )
    destination = _point(
        code=f"DST_{uuid4().hex[:8].upper()}",
        name_tr="Izmir",
        name_en="Izmir",
        latitude=38.42,
        longitude=27.14,
    )
    test_session.add_all([origin, destination])
    await test_session.flush()

    pair = RoutePair(
        route_pair_id=uuid4(),
        pair_code=_pair_code(),
        origin_location_id=origin.location_id,
        destination_location_id=destination.location_id,
        profile_code="TIR",
        pair_status="ACTIVE",
    )
    test_session.add(pair)
    await test_session.flush()

    forward_route = Route(
        route_id=uuid4(),
        route_pair_id=pair.route_pair_id,
        route_code=f"ROUTE-FWD-{uuid4().hex[:8].upper()}",
        direction="FORWARD",
        created_by="test",
    )
    reverse_route = Route(
        route_id=uuid4(),
        route_pair_id=pair.route_pair_id,
        route_code=f"ROUTE-REV-{uuid4().hex[:8].upper()}",
        direction="REVERSE",
        created_by="test",
    )
    test_session.add_all([forward_route, reverse_route])
    await test_session.flush()

    pair.forward_route_id = forward_route.route_id
    pair.reverse_route_id = reverse_route.route_id
    pair.current_active_forward_version_no = 1
    pair.current_active_reverse_version_no = 1
    test_session.add_all(
        [
            _route_version(forward_route.route_id, 1, 21600),
            _route_version(reverse_route.route_id, 1, 22800),
        ]
    )
    await test_session.commit()

    response = await client.get(f"/internal/v1/route-pairs/{pair.route_pair_id}/trip-context")

    assert response.status_code == 200
    body = response.json()
    assert body["pair_id"] == str(pair.route_pair_id)
    assert body["origin_name"] == "Istanbul"
    assert body["destination_name"] == "Izmir"
    assert body["forward_route_id"] == str(forward_route.route_id)
    assert body["forward_duration_s"] == 21600
    assert body["reverse_route_id"] == str(reverse_route.route_id)
    assert body["reverse_duration_s"] == 22800


@pytest.mark.asyncio
async def test_trip_context_missing_pair_returns_not_found(client: AsyncClient):
    response = await client.get(f"/internal/v1/route-pairs/{uuid4()}/trip-context")
    assert response.status_code == 404
    assert response.json()["code"] == "LOCATION_ROUTE_PAIR_NOT_FOUND"


@pytest.mark.asyncio
async def test_trip_context_inactive_pair_returns_conflict(client: AsyncClient, test_session):
    origin = _point(
        code=f"ORG_{uuid4().hex[:8].upper()}",
        name_tr="Konya",
        name_en="Konya",
        latitude=37.87,
        longitude=32.48,
    )
    destination = _point(
        code=f"DST_{uuid4().hex[:8].upper()}",
        name_tr="Bursa Draft",
        name_en="Bursa Draft",
        latitude=40.19,
        longitude=29.08,
    )
    test_session.add_all([origin, destination])
    await test_session.flush()

    pair = RoutePair(
        route_pair_id=uuid4(),
        pair_code=_pair_code(),
        origin_location_id=origin.location_id,
        destination_location_id=destination.location_id,
        profile_code="TIR",
        pair_status="DRAFT",
    )
    test_session.add(pair)
    await test_session.commit()

    response = await client.get(f"/internal/v1/route-pairs/{pair.route_pair_id}/trip-context")
    assert response.status_code == 409
    assert response.json()["code"] == "LOCATION_ROUTE_PAIR_NOT_ACTIVE_USE_CALCULATE"
