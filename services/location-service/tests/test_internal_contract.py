"""Contract tests: location-service internal API as consumed by trip-service.

These tests pin the exact response schema that trip-service depends on.
Any field rename, removal, or type change that breaks trip-service's
dependencies.py:244 / dependencies.py:282 will cause a failure here.

Reference consumer:
  services/trip-service/src/trip_service/dependencies.py
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from ulid import ULID

from location_service.domain.normalization import normalize_en, normalize_tr
from location_service.enums import PairStatus, ProcessingStatus
from location_service.models import LocationPoint, Route, RoutePair, RouteVersion


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _ulid() -> str:
    return str(ULID())


def _point(*, code: str, name_tr: str, name_en: str, lat: float, lon: float) -> LocationPoint:
    return LocationPoint(
        code=code,
        name_tr=name_tr,
        name_en=name_en,
        normalized_name_tr=normalize_tr(name_tr),
        normalized_name_en=normalize_en(name_en),
        latitude_6dp=lat,
        longitude_6dp=lon,
        is_active=True,
    )


def _active_version(route_id: str, duration_s: int) -> RouteVersion:
    return RouteVersion(
        route_id=route_id,
        version_no=1,
        processing_run_id=None,
        processing_status=ProcessingStatus.ACTIVE,
        total_distance_m=5000,
        total_duration_s=duration_s,
        total_ascent_m=None,
        total_descent_m=None,
        avg_grade_pct=None,
        max_grade_pct=None,
        steepest_downhill_pct=None,
        known_speed_limit_ratio=1,
        segment_count=1,
        validation_result="PASS",
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


async def _seed_active_pair(session, *, name_tr_origin: str, name_en_origin: str,
                             name_tr_dest: str, name_en_dest: str,
                             fwd_duration: int = 18000, rev_duration: int = 19000,
                             lat_origin: float = 39.0, lon_origin: float = 32.0,
                             lat_dest: float = 40.0, lon_dest: float = 29.0):
    origin = _point(
        code=f"CO{_ulid()}", name_tr=name_tr_origin, name_en=name_en_origin,
        lat=lat_origin, lon=lon_origin,
    )
    dest = _point(
        code=f"CD{_ulid()}", name_tr=name_tr_dest, name_en=name_en_dest,
        lat=lat_dest, lon=lon_dest,
    )
    session.add_all([origin, dest])
    await session.flush()

    pair = RoutePair(
        route_pair_id=_ulid(),
        pair_code=f"RP_{_ulid()}",
        origin_location_id=origin.location_id,
        destination_location_id=dest.location_id,
        profile_code="TIR",
        pair_status=PairStatus.ACTIVE,
    )
    session.add(pair)
    await session.flush()

    fwd = Route(route_id=_ulid(), route_pair_id=pair.route_pair_id,
                route_code=f"FWD-{_ulid()[:12]}", direction="FORWARD", created_by="test")
    rev = Route(route_id=_ulid(), route_pair_id=pair.route_pair_id,
                route_code=f"REV-{_ulid()[:12]}", direction="REVERSE", created_by="test")
    session.add_all([fwd, rev])
    await session.flush()

    pair.forward_route_id = fwd.route_id
    pair.reverse_route_id = rev.route_id
    pair.current_active_forward_version_no = 1
    pair.current_active_reverse_version_no = 1

    session.add_all([_active_version(fwd.route_id, fwd_duration),
                     _active_version(rev.route_id, rev_duration)])
    await session.commit()
    return pair, fwd, rev, origin, dest


# ---------------------------------------------------------------------------
# Contract: POST /internal/v1/routes/resolve
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolve_response_schema_has_all_required_fields(
    internal_client: AsyncClient, test_session
) -> None:
    """Pin the exact fields trip-service reads from the resolve response.

    Consumer reference: trip-service/dependencies.py resolve_route_pair()
    Expected fields: route_id, pair_id, resolution
    """
    pair, fwd, _rev, _o, _d = await _seed_active_pair(
        test_session,
        name_tr_origin="Ankara Kontrakt", name_en_origin="Ankara Contract",
        name_tr_dest="Bursa Kontrakt", name_en_dest="Bursa Contract",
    )

    response = await internal_client.post(
        "/internal/v1/routes/resolve",
        json={
            "origin_name": "Ankara Kontrakt",
            "destination_name": "Bursa Kontrakt",
            "profile_code": "TIR",
            "language_hint": "TR",
        },
    )

    assert response.status_code == 200
    body = response.json()

    # Every field trip-service reads must be present and non-null
    assert "route_id" in body, "route_id missing — trip-service reads this"
    assert "pair_id" in body, "pair_id missing — trip-service reads this"
    assert "resolution" in body, "resolution missing — trip-service reads this"

    assert isinstance(body["route_id"], str) and len(body["route_id"]) == 26
    assert isinstance(body["pair_id"], str) and len(body["pair_id"]) == 26
    assert body["resolution"] in ("EXACT_TR", "EXACT_EN"), \
        f"resolution must be EXACT_TR or EXACT_EN, got {body['resolution']!r}"

    # Values match what was seeded
    assert body["route_id"] == fwd.route_id
    assert body["pair_id"] == pair.route_pair_id


@pytest.mark.asyncio
async def test_resolve_not_found_error_schema(internal_client: AsyncClient) -> None:
    """Pin the 404 error body that trip-service handles.

    Consumer reference: trip-service/dependencies.py — catches LOCATION_ROUTE_RESOLUTION_NOT_FOUND
    """
    response = await internal_client.post(
        "/internal/v1/routes/resolve",
        json={"origin_name": "NonExistent City", "destination_name": "Also Nonexistent", "profile_code": "TIR"},
    )

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "LOCATION_ROUTE_RESOLUTION_NOT_FOUND", \
        "trip-service checks for this exact error code — do not rename it"
    assert "status" in body
    assert body["status"] == 404


@pytest.mark.asyncio
async def test_resolve_ambiguous_error_schema(internal_client: AsyncClient, test_session) -> None:
    """Pin the 422 ambiguous error body that trip-service handles.

    Consumer reference: trip-service/dependencies.py — catches ROUTE_AMBIGUOUS
    """
    # Create two active pairs that both match the same name
    await _seed_active_pair(
        test_session,
        name_tr_origin="Ambig Shared", name_en_origin="Ambig Alt1",
        name_tr_dest="Ambig Dest Shared", name_en_dest="Ambig Dest Alt1",
        lat_origin=50.0, lon_origin=20.0, lat_dest=51.0, lon_dest=21.0,
    )
    await _seed_active_pair(
        test_session,
        name_tr_origin="Ambig Alt2", name_en_origin="Ambig Shared",
        name_tr_dest="Ambig Dest Alt2", name_en_dest="Ambig Dest Shared",
        lat_origin=52.0, lon_origin=22.0, lat_dest=53.0, lon_dest=23.0,
    )

    response = await internal_client.post(
        "/internal/v1/routes/resolve",
        json={"origin_name": "Ambig Shared", "destination_name": "Ambig Dest Shared",
              "profile_code": "TIR", "language_hint": "AUTO"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "ROUTE_AMBIGUOUS", \
        "trip-service checks for this exact error code — do not rename it"


@pytest.mark.asyncio
async def test_resolve_requires_trip_service_token(raw_client: AsyncClient) -> None:
    """Internal routes must reject user tokens and unknown service tokens."""
    from conftest import ADMIN_HEADERS, SUPER_ADMIN_HEADERS, FORBIDDEN_SERVICE_HEADERS

    payload = {"origin_name": "X", "destination_name": "Y", "profile_code": "TIR"}

    for headers, label in [
        (ADMIN_HEADERS, "MANAGER user"),
        (SUPER_ADMIN_HEADERS, "SUPER_ADMIN user"),
        (FORBIDDEN_SERVICE_HEADERS, "other-service token"),
        ({}, "no token"),
    ]:
        r = await raw_client.post("/internal/v1/routes/resolve", json=payload, headers=headers)
        assert r.status_code in (401, 403), \
            f"{label} should be rejected (got {r.status_code})"


# ---------------------------------------------------------------------------
# Contract: GET /internal/v1/route-pairs/{pair_id}/trip-context
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trip_context_response_schema_has_all_required_fields(
    internal_client: AsyncClient, test_session
) -> None:
    """Pin the exact fields trip-service reads from the trip-context response.

    Consumer reference: trip-service/dependencies.py fetch_trip_context()
    Expected fields: pair_id, origin_location_id, origin_name,
                     destination_location_id, destination_name,
                     forward_route_id, forward_duration_s,
                     reverse_route_id, reverse_duration_s,
                     profile_code, pair_status
    """
    pair, fwd, rev, origin, dest = await _seed_active_pair(
        test_session,
        name_tr_origin="Istanbul Schema", name_en_origin="Istanbul Schema EN",
        name_tr_dest="Izmir Schema", name_en_dest="Izmir Schema EN",
        fwd_duration=21600, rev_duration=22800,
    )

    response = await internal_client.get(
        f"/internal/v1/route-pairs/{pair.route_pair_id}/trip-context"
    )

    assert response.status_code == 200
    body = response.json()

    required_fields = [
        "pair_id", "origin_location_id", "origin_name",
        "destination_location_id", "destination_name",
        "forward_route_id", "forward_duration_s",
        "reverse_route_id", "reverse_duration_s",
        "profile_code", "pair_status",
    ]
    for field in required_fields:
        assert field in body, f"trip-context field {field!r} missing — trip-service reads this"

    # Type and value assertions for each field
    assert body["pair_id"] == pair.route_pair_id
    assert body["origin_location_id"] == origin.location_id
    assert body["origin_name"] == "Istanbul Schema"
    assert body["destination_location_id"] == dest.location_id
    assert body["destination_name"] == "Izmir Schema"
    assert body["forward_route_id"] == fwd.route_id
    assert body["forward_duration_s"] == 21600
    assert body["reverse_route_id"] == rev.route_id
    assert body["reverse_duration_s"] == 22800
    assert body["profile_code"] == "TIR"
    assert body["pair_status"] == "ACTIVE"

    # ULID shape checks
    for field in ("pair_id", "origin_location_id", "destination_location_id",
                  "forward_route_id", "reverse_route_id"):
        assert isinstance(body[field], str) and len(body[field]) == 26, \
            f"{field} must be a 26-char ULID string"

    # Duration must be a non-negative integer
    assert isinstance(body["forward_duration_s"], int) and body["forward_duration_s"] >= 0
    assert isinstance(body["reverse_duration_s"], int) and body["reverse_duration_s"] >= 0


@pytest.mark.asyncio
async def test_trip_context_not_found_error_schema(internal_client: AsyncClient) -> None:
    """Pin the 404 error body that trip-service handles.

    Consumer reference: trip-service/dependencies.py — catches LOCATION_ROUTE_PAIR_NOT_FOUND
    """
    response = await internal_client.get(f"/internal/v1/route-pairs/{_ulid()}/trip-context")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "LOCATION_ROUTE_PAIR_NOT_FOUND", \
        "trip-service checks for this exact error code — do not rename it"
    assert body["status"] == 404


@pytest.mark.asyncio
async def test_trip_context_draft_pair_error_schema(internal_client: AsyncClient, test_session) -> None:
    """Pin the 409 error body for a DRAFT pair.

    Consumer reference: trip-service/dependencies.py — catches LOCATION_ROUTE_PAIR_NOT_ACTIVE_USE_CALCULATE
    """
    origin = _point(code=f"DR{_ulid()}", name_tr="Draft O", name_en="Draft O",
                    lat=36.0, lon=30.0)
    dest = _point(code=f"DR{_ulid()}", name_tr="Draft D", name_en="Draft D",
                  lat=36.5, lon=30.5)
    test_session.add_all([origin, dest])
    await test_session.flush()

    pair = RoutePair(
        route_pair_id=_ulid(), pair_code=f"RP_{_ulid()}",
        origin_location_id=origin.location_id,
        destination_location_id=dest.location_id,
        profile_code="TIR", pair_status=PairStatus.DRAFT,
    )
    test_session.add(pair)
    await test_session.commit()

    response = await internal_client.get(
        f"/internal/v1/route-pairs/{pair.route_pair_id}/trip-context"
    )
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "LOCATION_ROUTE_PAIR_NOT_ACTIVE_USE_CALCULATE", \
        "trip-service checks for this exact error code — do not rename it"


@pytest.mark.asyncio
async def test_trip_context_soft_deleted_pair_error_schema(
    internal_client: AsyncClient, test_session
) -> None:
    """Pin the 409 error body for a SOFT_DELETED pair.

    Consumer reference: trip-service/dependencies.py — catches LOCATION_ROUTE_PAIR_SOFT_DELETED
    """
    origin = _point(code=f"SD{_ulid()}", name_tr="Deleted O", name_en="Deleted O",
                    lat=35.0, lon=29.0)
    dest = _point(code=f"SD{_ulid()}", name_tr="Deleted D", name_en="Deleted D",
                  lat=35.5, lon=29.5)
    test_session.add_all([origin, dest])
    await test_session.flush()

    pair = RoutePair(
        route_pair_id=_ulid(), pair_code=f"RP_{_ulid()}",
        origin_location_id=origin.location_id,
        destination_location_id=dest.location_id,
        profile_code="TIR", pair_status=PairStatus.SOFT_DELETED,
    )
    test_session.add(pair)
    await test_session.commit()

    response = await internal_client.get(
        f"/internal/v1/route-pairs/{pair.route_pair_id}/trip-context"
    )
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "LOCATION_ROUTE_PAIR_SOFT_DELETED", \
        "trip-service checks for this exact error code — do not rename it"


@pytest.mark.asyncio
async def test_trip_context_requires_trip_service_token(raw_client: AsyncClient) -> None:
    """Internal routes must reject user tokens and unknown service tokens."""
    from conftest import ADMIN_HEADERS, SUPER_ADMIN_HEADERS, FORBIDDEN_SERVICE_HEADERS

    for headers, label in [
        (ADMIN_HEADERS, "MANAGER user"),
        (SUPER_ADMIN_HEADERS, "SUPER_ADMIN user"),
        (FORBIDDEN_SERVICE_HEADERS, "other-service token"),
        ({}, "no token"),
    ]:
        r = await raw_client.get(
            f"/internal/v1/route-pairs/{_ulid()}/trip-context", headers=headers
        )
        assert r.status_code in (401, 403), \
            f"{label} should be rejected (got {r.status_code})"
