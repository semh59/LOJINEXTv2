"""Contract tests for Location Route Pairs API (Section 22)."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_get_pair(client: AsyncClient) -> None:
    """Test pair creation requires valid points and avoids duplicates."""
    # Create points
    p1 = await client.post(
        "/v1/points",
        json={"code": "PAIR_O", "name_tr": "O_TR_1", "name_en": "O_EN_1", "latitude_6dp": 10.0, "longitude_6dp": 10.0},
    )
    p2 = await client.post(
        "/v1/points",
        json={"code": "PAIR_D", "name_tr": "D_TR_1", "name_en": "D_EN_1", "latitude_6dp": 20.0, "longitude_6dp": 20.0},
    )

    # Create pair
    pair_resp = await client.post(
        "/v1/pairs",
        json={
            "origin_code": "PAIR_O",
            "destination_code": "PAIR_D",
        },
    )
    assert pair_resp.status_code == 201
    pair_data = pair_resp.json()
    assert pair_data["origin_location_id"] == p1.json()["location_id"]
    assert pair_data["destination_location_id"] == p2.json()["location_id"]
    assert pair_data["pair_code"].startswith("RP_")

    # Duplicate fails
    dup_resp = await client.post(
        "/v1/pairs",
        json={
            "origin_code": "PAIR_O",
            "destination_code": "PAIR_D",
        },
    )
    assert dup_resp.status_code == 409


@pytest.mark.asyncio
async def test_calculate_trigger(client: AsyncClient) -> None:
    """Test the calculate dispatch endpoint."""
    # Create pair first
    await client.post(
        "/v1/points",
        json={"code": "TRIG_O", "name_tr": "O_TR_2", "name_en": "O_EN_2", "latitude_6dp": 30.0, "longitude_6dp": 30.0},
    )
    await client.post(
        "/v1/points",
        json={"code": "TRIG_D", "name_tr": "D_TR_2", "name_en": "D_EN_2", "latitude_6dp": 40.0, "longitude_6dp": 40.0},
    )

    p_resp = await client.post(
        "/v1/pairs",
        json={
            "origin_code": "TRIG_O",
            "destination_code": "TRIG_D",
        },
    )
    pair_id = p_resp.json()["pair_id"]

    # Trigger calculation
    calc_resp = await client.post(f"/v1/pairs/{pair_id}/calculate")
    assert calc_resp.status_code == 202
    calc_data = calc_resp.json()
    assert calc_data["pair_id"] == pair_id
    assert calc_data["run_status"] == "QUEUED"
    assert "run_id" in calc_data
