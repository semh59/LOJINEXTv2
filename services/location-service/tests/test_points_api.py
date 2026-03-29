"""Contract tests for Location Points API."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


def _point_payload(*, code: str, name_tr: str, name_en: str, latitude: float, longitude: float, is_active: bool = True):
    return {
        "code": code,
        "name_tr": name_tr,
        "name_en": name_en,
        "latitude_6dp": latitude,
        "longitude_6dp": longitude,
        "is_active": is_active,
    }


@pytest.mark.asyncio
async def test_create_and_get_point(client: AsyncClient) -> None:
    payload = _point_payload(
        code="TR_IST_01",
        name_tr="Istanbul Merkez",
        name_en="Istanbul Center",
        latitude=41.0082111,
        longitude=28.9784,
    )

    response = await client.post("/v1/points", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert response.headers["etag"] == '"1"'
    assert data["code"] == "TR_IST_01"
    assert data["normalized_name_tr"] == "ISTANBUL MERKEZ"
    assert data["latitude_6dp"] == 41.008211
    assert data["row_version"] == 1

    get_response = await client.get(f"/v1/points/{data['location_id']}")
    assert get_response.status_code == 200
    assert get_response.headers["etag"] == '"1"'
    assert get_response.json()["code"] == "TR_IST_01"


@pytest.mark.asyncio
async def test_create_point_missing_fields_returns_problem_json(client: AsyncClient) -> None:
    response = await client.post("/v1/points", json={"code": "MISS_01"})
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == "LOCATION_REQUEST_VALIDATION_ERROR"
    assert any(error["field"].startswith("body.") for error in body["errors"])


@pytest.mark.asyncio
async def test_create_point_blank_name_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/points",
        json=_point_payload(code="BLANK_01", name_tr="   ", name_en="Valid Name", latitude=39.0, longitude=32.0),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "LOCATION_POINT_NAME_BLANK"


@pytest.mark.asyncio
async def test_update_point_rejects_immutable_fields(client: AsyncClient) -> None:
    create_response = await client.post(
        "/v1/points",
        json=_point_payload(
            code="IMM_01", name_tr="Immutable Point", name_en="Immutable Point", latitude=38.0, longitude=27.0
        ),
    )
    point = create_response.json()

    patch_response = await client.patch(
        f"/v1/points/{point['location_id']}",
        json={"code": "NEW_CODE"},
        headers={"If-Match": f'"{point["row_version"]}"'},
    )
    assert patch_response.status_code == 422
    assert patch_response.headers["content-type"].startswith("application/problem+json")
    assert patch_response.json()["code"] == "LOCATION_POINT_IMMUTABLE_FIELD_MODIFICATION"


@pytest.mark.asyncio
async def test_update_point_requires_if_match(client: AsyncClient) -> None:
    create_response = await client.post(
        "/v1/points",
        json=_point_payload(code="IFMATCH_01", name_tr="If Match", name_en="If Match", latitude=37.0, longitude=26.0),
    )
    point = create_response.json()

    patch_response = await client.patch(
        f"/v1/points/{point['location_id']}",
        json={"name_tr": "If Match New"},
    )
    assert patch_response.status_code == 428
    assert patch_response.json()["code"] == "LOCATION_IF_MATCH_REQUIRED"


@pytest.mark.asyncio
async def test_update_point_name_conflict_and_row_version_increment(client: AsyncClient) -> None:
    await client.post(
        "/v1/points",
        json=_point_payload(
            code="CONFLICT_A", name_tr="Ankara Ana", name_en="Ankara Main", latitude=39.92, longitude=32.85
        ),
    )
    second_response = await client.post(
        "/v1/points",
        json=_point_payload(
            code="CONFLICT_B", name_tr="Izmir Ana", name_en="Izmir Main", latitude=38.42, longitude=27.14
        ),
    )
    second = second_response.json()

    conflict_response = await client.patch(
        f"/v1/points/{second['location_id']}",
        json={"name_tr": "Ankara Ana"},
        headers={"If-Match": f'"{second["row_version"]}"'},
    )
    assert conflict_response.status_code == 409
    assert conflict_response.json()["code"] == "LOCATION_POINT_NAME_CONFLICT"

    success_response = await client.patch(
        f"/v1/points/{second['location_id']}",
        json={"name_tr": "Izmir Yeni"},
        headers={"If-Match": f'"{second["row_version"]}"'},
    )
    assert success_response.status_code == 200
    assert success_response.headers["etag"] == '"2"'
    assert success_response.json()["row_version"] == second["row_version"] + 1


@pytest.mark.asyncio
async def test_list_points_filters_search_pagination_and_sort(client: AsyncClient) -> None:
    first = await client.post(
        "/v1/points",
        json=_point_payload(code="LIST_A", name_tr="Alpha LST", name_en="Alpha LST", latitude=5.0, longitude=5.0),
    )
    second = await client.post(
        "/v1/points",
        json=_point_payload(
            code="LIST_B", name_tr="Beta LST", name_en="Beta LST", latitude=6.0, longitude=6.0, is_active=False
        ),
    )
    third = await client.post(
        "/v1/points",
        json=_point_payload(code="LIST_C", name_tr="Gamma LST", name_en="Gamma LST", latitude=7.0, longitude=7.0),
    )

    updated = await client.patch(
        f"/v1/points/{first.json()['location_id']}",
        json={"name_tr": "Alpha LST Updated"},
        headers={"If-Match": first.headers["etag"]},
    )
    assert updated.status_code == 200

    active_response = await client.get("/v1/points?is_active=true")
    assert active_response.status_code == 200
    assert all(item["is_active"] is True for item in active_response.json()["data"])

    inactive_response = await client.get("/v1/points?is_active=false")
    assert inactive_response.status_code == 200
    assert inactive_response.json()["data"][0]["code"] == "LIST_B"

    search_response = await client.get("/v1/points?search=Alpha")
    assert search_response.status_code == 200
    assert [item["code"] for item in search_response.json()["data"]] == ["LIST_A"]

    per_page_response = await client.get("/v1/points?page=1&per_page=1")
    assert per_page_response.status_code == 200
    assert len(per_page_response.json()["data"]) == 1
    assert per_page_response.json()["meta"]["per_page"] == 1

    limit_response = await client.get("/v1/points?page=1&limit=2")
    assert limit_response.status_code == 200
    assert len(limit_response.json()["data"]) == 2
    assert limit_response.json()["meta"]["per_page"] == 2

    both_response = await client.get("/v1/points?page=1&per_page=1&limit=3")
    assert both_response.status_code == 200
    assert len(both_response.json()["data"]) == 1
    assert both_response.json()["meta"]["per_page"] == 1

    default_sort_response = await client.get("/v1/points")
    assert default_sort_response.status_code == 200
    assert default_sort_response.json()["meta"]["sort"] == "updated_at_utc:desc"
    assert default_sort_response.json()["data"][0]["code"] == "LIST_A"

    sort_response = await client.get("/v1/points?sort=code:asc")
    assert sort_response.status_code == 200
    assert [item["code"] for item in sort_response.json()["data"][:3]] == ["LIST_A", "LIST_B", "LIST_C"]

    invalid_sort = await client.get("/v1/points?sort=bogus:desc")
    assert invalid_sort.status_code == 422
    assert invalid_sort.headers["content-type"].startswith("application/problem+json")
    assert invalid_sort.json()["code"] == "LOCATION_REQUEST_VALIDATION_ERROR"

    assert second.status_code == 201
    assert third.status_code == 201
