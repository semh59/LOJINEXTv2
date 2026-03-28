"""Contract tests for Location Points API (Section 22)."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_get_point(client: AsyncClient) -> None:
    """Test point creation, normalization, and retrieval."""
    payload = {
        "code": "TR_IST_01",
        "name_tr": "\u0130stanbul Merkez",
        "name_en": "Istanbul Center",
        "latitude_6dp": 41.0082111,
        "longitude_6dp": 28.978400,
        "is_active": True,
    }

    # 1. Create
    resp = await client.post("/v1/points", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["code"] == "TR_IST_01"
    assert data["normalized_name_tr"] == "\u0130STANBUL MERKEZ"
    assert data["latitude_6dp"] == 41.008211  # rounded to 6dp
    point_id = data["location_id"]

    # 2. Get
    get_resp = await client.get(f"/v1/points/{point_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["code"] == "TR_IST_01"


@pytest.mark.asyncio
async def test_update_point(client: AsyncClient) -> None:
    """Test partial update of points."""
    # Create first
    resp = await client.post(
        "/v1/points",
        json={
            "code": "UPDATE_01",
            "name_tr": "Eski Isim Upd",
            "name_en": "Old Name Upd",
            "latitude_6dp": 8.0,
            "longitude_6dp": 8.0,
        },
    )
    point_data = resp.json()
    point_id = point_data["location_id"]
    etag = f"\"{point_data['row_version']}\""

    # Update TR name
    patch_resp = await client.patch(
        f"/v1/points/{point_id}",
        json={"name_tr": "Yeni \u0130sim"},
        headers={"If-Match": etag},
    )
    assert patch_resp.status_code == 200
    patch_data = patch_resp.json()
    assert patch_data["name_tr"] == "Yeni \u0130sim"
    assert patch_data["normalized_name_tr"] == "YEN\u0130 \u0130S\u0130M"
    assert patch_data["name_en"] == "Old Name Upd"
    assert patch_data["row_version"] == 2


@pytest.mark.asyncio
async def test_list_points(client: AsyncClient) -> None:
    """Test pagination, search, and filtering."""
    # Ensure items exist
    await client.post(
        "/v1/points",
        json={
            "code": "LIST_A",
            "name_tr": "Alpha LST",
            "name_en": "Alpha LST",
            "latitude_6dp": 5.0,
            "longitude_6dp": 5.0,
            "is_active": True,
        },
    )
    await client.post(
        "/v1/points",
        json={
            "code": "LIST_B",
            "name_tr": "Beta LST",
            "name_en": "Beta LST",
            "latitude_6dp": 6.0,
            "longitude_6dp": 6.0,
            "is_active": False,
        },
    )

    # Filter active
    resp = await client.get("/v1/points?is_active=true")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["data"]) >= 1
    assert all(d["is_active"] is True for d in data["data"])
    assert data["meta"]["page"] == 1

    # Search
    search_resp = await client.get("/v1/points?search=Alpha")
    assert search_resp.status_code == 200
    search_data = search_resp.json()["data"]
    assert len(search_data) == 1
    assert search_data[0]["code"] == "LIST_A"
