"""Contract tests for Location Route Pairs API."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from location_service.enums import DirectionCode, PairStatus, ProcessingStatus
from location_service.models import Route, RoutePair, RouteVersion


async def _create_point(
    client: AsyncClient,
    *,
    code: str,
    latitude: float,
    longitude: float,
    name: str | None = None,
) -> None:
    response = await client.post(
        "/v1/points",
        json={
            "code": code,
            "name_tr": name or f"{code} TR",
            "name_en": name or f"{code} EN",
            "latitude_6dp": latitude,
            "longitude_6dp": longitude,
            "is_active": True,
        },
    )
    assert response.status_code == 201
    assert response.headers["etag"] == '"1"'


async def _create_pair(
    client: AsyncClient,
    *,
    origin_code: str,
    destination_code: str,
    profile_code: str = "TIR",
) -> dict[str, object]:
    response = await client.post(
        "/v1/pairs",
        json={"origin_code": origin_code, "destination_code": destination_code, "profile_code": profile_code},
    )
    assert response.status_code == 201
    assert response.headers["etag"] == '"1"'
    return response.json()


async def _load_pair(test_session: AsyncSession, pair_id: str) -> RoutePair:
    pair = (await test_session.execute(select(RoutePair).where(RoutePair.route_pair_id == UUID(pair_id)))).scalar_one()
    return pair


async def _seed_pending_draft(test_session: AsyncSession, pair_id: str) -> RoutePair:
    pair = await _load_pair(test_session, pair_id)

    forward_route = Route(
        route_id=uuid4(),
        route_pair_id=pair.route_pair_id,
        route_code=f"ROUTE-FWD-{uuid4().hex[:8].upper()}",
        direction=DirectionCode.FORWARD,
        created_by="test",
    )
    reverse_route = Route(
        route_id=uuid4(),
        route_pair_id=pair.route_pair_id,
        route_code=f"ROUTE-REV-{uuid4().hex[:8].upper()}",
        direction=DirectionCode.REVERSE,
        created_by="test",
    )
    test_session.add_all([forward_route, reverse_route])
    await test_session.flush()

    pair.forward_route_id = forward_route.route_id
    pair.reverse_route_id = reverse_route.route_id
    pair.pending_forward_version_no = 1
    pair.pending_reverse_version_no = 1

    shared_payload = {
        "processing_run_id": None,
        "total_distance_m": 1000,
        "total_duration_s": 1000,
        "segment_count": 1,
        "validation_result": "PASS",
        "known_speed_limit_ratio": 1.0,
        "field_origin_matrix_json": {},
        "field_origin_matrix_hash": "hash",
        "road_type_distribution_json": {},
        "speed_limit_distribution_json": {},
        "urban_distribution_json": {},
        "warnings_json": [],
        "processing_algorithm_version": "v1",
    }
    test_session.add_all(
        [
            RouteVersion(
                route_id=forward_route.route_id,
                version_no=1,
                processing_status=ProcessingStatus.CALCULATED_DRAFT,
                **shared_payload,
            ),
            RouteVersion(
                route_id=reverse_route.route_id,
                version_no=1,
                processing_status=ProcessingStatus.CALCULATED_DRAFT,
                **shared_payload,
            ),
        ]
    )
    await test_session.commit()
    await test_session.refresh(pair)
    return pair


@pytest.mark.asyncio
async def test_create_and_get_pair_returns_frontend_complete_payload(client: AsyncClient) -> None:
    await _create_point(client, code="PAIR_O", latitude=10.0, longitude=10.0, name="Pair Origin")
    await _create_point(client, code="PAIR_D", latitude=20.0, longitude=20.0, name="Pair Destination")

    pair = await _create_pair(client, origin_code="PAIR_O", destination_code="PAIR_D")
    create_response = await client.get(f"/v1/pairs/{pair['pair_id']}")
    assert pair["pair_code"].startswith("RP_")
    assert pair["status"] == "DRAFT"
    assert pair["row_version"] == 1
    assert pair["profile_code"] == "TIR"
    assert pair["origin_code"] == "PAIR_O"
    assert pair["origin_name_tr"] == "Pair Origin"
    assert pair["destination_code"] == "PAIR_D"
    assert pair["destination_name_tr"] == "Pair Destination"
    assert pair["forward_route_id"] is None
    assert pair["reverse_route_id"] is None
    assert pair["has_pending_draft"] is False

    assert create_response.status_code == 200
    assert create_response.headers["etag"] == '"1"'
    assert create_response.json()["pair_id"] == pair["pair_id"]


@pytest.mark.asyncio
async def test_get_pair_includes_route_pointers_and_pending_draft_state(client: AsyncClient, db_engine) -> None:
    await _create_point(client, code="PTR_O", latitude=11.0, longitude=11.0)
    await _create_point(client, code="PTR_D", latitude=12.0, longitude=12.0)
    pair = await _create_pair(client, origin_code="PTR_O", destination_code="PTR_D")

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        model = await _seed_pending_draft(session, pair["pair_id"])

    response = await client.get(f"/v1/pairs/{pair['pair_id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["forward_route_id"] == str(model.forward_route_id)
    assert body["reverse_route_id"] == str(model.reverse_route_id)
    assert body["has_pending_draft"] is True
    assert body["draft_forward_version_no"] == 1
    assert body["draft_reverse_version_no"] == 1


@pytest.mark.asyncio
async def test_create_pair_soft_deleted_duplicate_returns_deleted(client: AsyncClient) -> None:
    await _create_point(client, code="SOFT_O", latitude=11.5, longitude=11.5)
    await _create_point(client, code="SOFT_D", latitude=21.5, longitude=21.5)
    pair = await _create_pair(client, origin_code="SOFT_O", destination_code="SOFT_D")

    delete_response = await client.delete(
        f"/v1/pairs/{pair['pair_id']}",
        headers={"If-Match": f'"{pair["row_version"]}"'},
    )
    assert delete_response.status_code == 204

    recreate_response = await client.post(
        "/v1/pairs",
        json={"origin_code": "SOFT_O", "destination_code": "SOFT_D", "profile_code": "TIR"},
    )
    assert recreate_response.status_code == 409
    assert recreate_response.json()["code"] == "LOCATION_ROUTE_PAIR_ALREADY_EXISTS_DELETED"


@pytest.mark.asyncio
async def test_list_pairs_filters_search_profile_pagination_and_sort(client: AsyncClient) -> None:
    await _create_point(client, code="LIST_O1", latitude=30.0, longitude=30.0, name="Search Origin One")
    await _create_point(client, code="LIST_D1", latitude=31.0, longitude=31.0, name="Search Destination One")
    await _create_point(client, code="LIST_O2", latitude=32.0, longitude=32.0, name="Search Origin Two")
    await _create_point(client, code="LIST_D2", latitude=33.0, longitude=33.0, name="Search Destination Two")
    await _create_point(client, code="LIST_O3", latitude=34.0, longitude=34.0, name="Search Origin Three")
    await _create_point(client, code="LIST_D3", latitude=35.0, longitude=35.0, name="Search Destination Three")

    first = await _create_pair(client, origin_code="LIST_O1", destination_code="LIST_D1", profile_code="TIR")
    second = await _create_pair(client, origin_code="LIST_O2", destination_code="LIST_D2", profile_code="VAN")
    third = await _create_pair(client, origin_code="LIST_O3", destination_code="LIST_D3", profile_code="TIR")

    patched = await client.patch(
        f"/v1/pairs/{first['pair_id']}",
        json={"profile_code": "VAN"},
        headers={"If-Match": f'"{first["row_version"]}"'},
    )
    assert patched.status_code == 200

    active_response = await client.get("/v1/pairs?is_active=true")
    assert active_response.status_code == 200
    assert active_response.json()["data"] == []

    inactive_response = await client.get("/v1/pairs?is_active=false")
    assert inactive_response.status_code == 200
    assert len(inactive_response.json()["data"]) == 3
    assert {item["status"] for item in inactive_response.json()["data"]} == {"DRAFT"}

    profile_response = await client.get("/v1/pairs?profile_code=VAN")
    assert profile_response.status_code == 200
    assert {item["pair_id"] for item in profile_response.json()["data"]} == {first["pair_id"], second["pair_id"]}

    search_by_code = await client.get("/v1/pairs?search=LIST_O2")
    assert search_by_code.status_code == 200
    assert [item["pair_id"] for item in search_by_code.json()["data"]] == [second["pair_id"]]

    search_by_name = await client.get("/v1/pairs?search=Destination Three")
    assert search_by_name.status_code == 200
    assert [item["pair_id"] for item in search_by_name.json()["data"]] == [third["pair_id"]]

    per_page_response = await client.get("/v1/pairs?page=1&per_page=1")
    assert per_page_response.status_code == 200
    assert len(per_page_response.json()["data"]) == 1
    assert per_page_response.json()["meta"]["per_page"] == 1

    limit_response = await client.get("/v1/pairs?page=1&limit=2")
    assert limit_response.status_code == 200
    assert len(limit_response.json()["data"]) == 2
    assert limit_response.json()["meta"]["per_page"] == 2

    both_response = await client.get("/v1/pairs?page=1&per_page=1&limit=3")
    assert both_response.status_code == 200
    assert len(both_response.json()["data"]) == 1
    assert both_response.json()["meta"]["per_page"] == 1

    default_sort_response = await client.get("/v1/pairs")
    assert default_sort_response.status_code == 200
    assert default_sort_response.json()["meta"]["sort"] == "updated_at_utc:desc"
    assert default_sort_response.json()["data"][0]["pair_id"] == first["pair_id"]

    pair_code_sort = await client.get("/v1/pairs?sort=pair_code:asc")
    assert pair_code_sort.status_code == 200
    pair_codes = [item["pair_code"] for item in pair_code_sort.json()["data"]]
    assert pair_codes == sorted(pair_codes)

    invalid_sort = await client.get("/v1/pairs?sort=bogus:desc")
    assert invalid_sort.status_code == 422
    assert invalid_sort.headers["content-type"].startswith("application/problem+json")
    assert invalid_sort.json()["code"] == "LOCATION_REQUEST_VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_list_pairs_hides_soft_deleted_by_default(client: AsyncClient) -> None:
    await _create_point(client, code="SOFTLIST_O1", latitude=60.0, longitude=60.0)
    await _create_point(client, code="SOFTLIST_D1", latitude=61.0, longitude=61.0)
    await _create_point(client, code="SOFTLIST_O2", latitude=62.0, longitude=62.0)
    await _create_point(client, code="SOFTLIST_D2", latitude=63.0, longitude=63.0)

    live_pair = await _create_pair(client, origin_code="SOFTLIST_O1", destination_code="SOFTLIST_D1")
    deleted_pair = await _create_pair(client, origin_code="SOFTLIST_O2", destination_code="SOFTLIST_D2")

    delete_response = await client.delete(
        f"/v1/pairs/{deleted_pair['pair_id']}",
        headers={"If-Match": f'"{deleted_pair["row_version"]}"'},
    )
    default_list = await client.get("/v1/pairs")
    draft_list = await client.get("/v1/pairs?is_active=false")
    deleted_list = await client.get("/v1/pairs?status=SOFT_DELETED")

    assert delete_response.status_code == 204
    assert {item["pair_id"] for item in default_list.json()["data"]} == {live_pair["pair_id"]}
    assert {item["pair_id"] for item in draft_list.json()["data"]} == {live_pair["pair_id"]}
    assert {item["pair_id"] for item in deleted_list.json()["data"]} == {deleted_pair["pair_id"]}


@pytest.mark.asyncio
async def test_list_pairs_rejects_conflicting_status_and_is_active_filters(client: AsyncClient) -> None:
    response = await client.get("/v1/pairs?status=ACTIVE&is_active=false")
    assert response.status_code == 422
    assert response.json()["code"] == "LOCATION_INVALID_FILTER_COMBINATION"


@pytest.mark.asyncio
async def test_patch_pair_requires_if_match_and_increments_row_version(client: AsyncClient) -> None:
    await _create_point(client, code="PATCH_O", latitude=40.0, longitude=40.0)
    await _create_point(client, code="PATCH_D", latitude=41.0, longitude=41.0)
    pair = await _create_pair(client, origin_code="PATCH_O", destination_code="PATCH_D")

    missing_header = await client.patch(f"/v1/pairs/{pair['pair_id']}", json={"profile_code": "VAN"})
    assert missing_header.status_code == 428
    assert missing_header.json()["code"] == "LOCATION_IF_MATCH_REQUIRED"

    stale_header = await client.patch(
        f"/v1/pairs/{pair['pair_id']}",
        json={"profile_code": "VAN"},
        headers={"If-Match": '"99"'},
    )
    assert stale_header.status_code == 412
    assert stale_header.json()["code"] == "LOCATION_ROUTE_PAIR_VERSION_MISMATCH"

    success_response = await client.patch(
        f"/v1/pairs/{pair['pair_id']}",
        json={"profile_code": "VAN"},
        headers={"If-Match": f'"{pair["row_version"]}"'},
    )
    assert success_response.status_code == 200
    assert success_response.headers["etag"] == '"2"'
    body = success_response.json()
    assert body["row_version"] == pair["row_version"] + 1
    assert body["profile_code"] == "VAN"

    stale_after_update = await client.patch(
        f"/v1/pairs/{pair['pair_id']}",
        json={"profile_code": "TIR"},
        headers={"If-Match": f'"{pair["row_version"]}"'},
    )
    assert stale_after_update.status_code == 412
    assert stale_after_update.json()["code"] == "LOCATION_ROUTE_PAIR_VERSION_MISMATCH"

    duplicate_after_update = await client.post(
        "/v1/pairs",
        json={"origin_code": "PATCH_O", "destination_code": "PATCH_D", "profile_code": "VAN"},
    )
    assert duplicate_after_update.status_code == 409
    assert duplicate_after_update.json()["code"] == "LOCATION_ROUTE_PAIR_ALREADY_EXISTS_ACTIVE"


@pytest.mark.asyncio
async def test_create_pair_maps_live_unique_index_violation_to_conflict(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _create_point(client, code="RACE_O", latitude=64.0, longitude=64.0)
    await _create_point(client, code="RACE_D", latitude=65.0, longitude=65.0)
    await _create_pair(client, origin_code="RACE_O", destination_code="RACE_D")

    async def skip_uniqueness(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr("location_service.routers.pairs._assert_pair_uniqueness", skip_uniqueness)

    response = await client.post(
        "/v1/pairs",
        json={"origin_code": "RACE_O", "destination_code": "RACE_D", "profile_code": "TIR"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "LOCATION_ROUTE_PAIR_ALREADY_EXISTS_ACTIVE"


@pytest.mark.asyncio
async def test_patch_pair_rejects_is_active_field(client: AsyncClient) -> None:
    await _create_point(client, code="PATCH2_O", latitude=42.0, longitude=42.0)
    await _create_point(client, code="PATCH2_D", latitude=43.0, longitude=43.0)
    pair = await _create_pair(client, origin_code="PATCH2_O", destination_code="PATCH2_D")

    response = await client.patch(
        f"/v1/pairs/{pair['pair_id']}",
        json={"is_active": True},
        headers={"If-Match": f'"{pair["row_version"]}"'},
    )
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "LOCATION_REQUEST_VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_calculate_active_pair_requires_refresh(client: AsyncClient, test_session: AsyncSession) -> None:
    await _create_point(client, code="CALC_O", latitude=44.0, longitude=44.0)
    await _create_point(client, code="CALC_D", latitude=45.0, longitude=45.0)
    pair = await _create_pair(client, origin_code="CALC_O", destination_code="CALC_D")

    model = await _load_pair(test_session, pair["pair_id"])
    model.pair_status = PairStatus.ACTIVE
    await test_session.commit()

    response = await client.post(f"/v1/pairs/{pair['pair_id']}/calculate", json={})
    assert response.status_code == 409
    assert response.json()["code"] == "LOCATION_ROUTE_PAIR_ALREADY_ACTIVE_USE_REFRESH"


@pytest.mark.asyncio
async def test_refresh_draft_pair_requires_calculate(client: AsyncClient) -> None:
    await _create_point(client, code="REFRESH_O", latitude=46.0, longitude=46.0)
    await _create_point(client, code="REFRESH_D", latitude=47.0, longitude=47.0)
    pair = await _create_pair(client, origin_code="REFRESH_O", destination_code="REFRESH_D")

    response = await client.post(f"/v1/pairs/{pair['pair_id']}/refresh")
    assert response.status_code == 409
    assert response.json()["code"] == "LOCATION_ROUTE_PAIR_NOT_ACTIVE_USE_CALCULATE"


@pytest.mark.asyncio
async def test_calculate_trigger_returns_expanded_run_metadata(client: AsyncClient) -> None:
    await _create_point(client, code="TRIG_O", latitude=48.0, longitude=48.0)
    await _create_point(client, code="TRIG_D", latitude=49.0, longitude=49.0)
    pair = await _create_pair(client, origin_code="TRIG_O", destination_code="TRIG_D")

    response = await client.post(f"/v1/pairs/{pair['pair_id']}/calculate", json={})
    assert response.status_code == 202
    body = response.json()
    assert body["pair_id"] == pair["pair_id"]
    assert body["pair_code"] == pair["pair_code"]
    assert body["run_status"] == "QUEUED"
    assert body["trigger_type"] == "INITIAL_CALCULATE"
    assert body["attempt_no"] == 1
    assert "provider_mapbox_status" in body
    assert "provider_ors_status" in body


@pytest.mark.asyncio
async def test_delete_pair_requires_if_match(client: AsyncClient) -> None:
    await _create_point(client, code="DEL_O", latitude=50.0, longitude=50.0)
    await _create_point(client, code="DEL_D", latitude=51.0, longitude=51.0)
    pair = await _create_pair(client, origin_code="DEL_O", destination_code="DEL_D")

    response = await client.delete(f"/v1/pairs/{pair['pair_id']}")
    assert response.status_code == 428
    assert response.json()["code"] == "LOCATION_IF_MATCH_REQUIRED"


@pytest.mark.asyncio
async def test_approve_pair_requires_if_match_and_returns_frontend_payload(
    client: AsyncClient,
    db_engine,
) -> None:
    await _create_point(client, code="APPROVE_O", latitude=52.0, longitude=52.0)
    await _create_point(client, code="APPROVE_D", latitude=53.0, longitude=53.0)
    pair = await _create_pair(client, origin_code="APPROVE_O", destination_code="APPROVE_D")
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        await _seed_pending_draft(session, pair["pair_id"])

    missing_header = await client.post(f"/v1/pairs/{pair['pair_id']}/approve")
    assert missing_header.status_code == 428
    assert missing_header.json()["code"] == "LOCATION_IF_MATCH_REQUIRED"

    current = await client.get(f"/v1/pairs/{pair['pair_id']}")
    approved = await client.post(
        f"/v1/pairs/{pair['pair_id']}/approve",
        headers={"If-Match": current.headers["etag"]},
    )
    assert approved.status_code == 200
    assert approved.headers["etag"] == '"2"'
    body = approved.json()
    assert body["status"] == "ACTIVE"
    assert body["origin_code"] == "APPROVE_O"
    assert body["destination_code"] == "APPROVE_D"


@pytest.mark.asyncio
async def test_discard_pair_returns_pair_response_and_etag(client: AsyncClient, db_engine) -> None:
    await _create_point(client, code="DISCARD_O", latitude=54.0, longitude=54.0)
    await _create_point(client, code="DISCARD_D", latitude=55.0, longitude=55.0)
    pair = await _create_pair(client, origin_code="DISCARD_O", destination_code="DISCARD_D")
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        await _seed_pending_draft(session, pair["pair_id"])

    current = await client.get(f"/v1/pairs/{pair['pair_id']}")
    discarded = await client.post(
        f"/v1/pairs/{pair['pair_id']}/discard",
        headers={"If-Match": current.headers["etag"]},
    )
    assert discarded.status_code == 200
    assert discarded.headers["etag"] == '"2"'
    assert discarded.json()["status"] == "DRAFT"


@pytest.mark.asyncio
async def test_activate_endpoint_returns_removed_tombstone(client: AsyncClient) -> None:
    response = await client.post(f"/v1/pairs/{uuid4()}/activate")
    assert response.status_code == 404
    assert response.json()["code"] == "LOCATION_ENDPOINT_REMOVED"
