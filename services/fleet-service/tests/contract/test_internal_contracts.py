import pytest
from httpx import AsyncClient

from tests.conftest import SERVICE_HEADERS


@pytest.mark.asyncio
async def test_internal_validate_endpoints(client: AsyncClient):
    # 1. Create a vehicle and trailer to validate
    create_hdrs = {**SERVICE_HEADERS, "X-Idempotency-Key": "internal-test-01"}
    v_resp = await client.post(
        "/api/v1/vehicles",
        json={"asset_code": "V-INT-01", "plate": "34 INT 01", "ownership_type": "OWNED"},
        headers=create_hdrs,
    )
    vehicle_id = v_resp.json()["vehicle_id"]

    t_hdrs = {**SERVICE_HEADERS, "X-Idempotency-Key": "internal-test-02"}
    t_resp = await client.post(
        "/api/v1/trailers",
        json={"asset_code": "T-INT-01", "plate": "34 INT 55", "ownership_type": "LEASED"},
        headers=t_hdrs,
    )
    trailer_id = t_resp.json()["trailer_id"]

    # 2. Validate single vehicle
    resp = await client.get(f"/internal/v1/vehicles/{vehicle_id}/validate", headers=SERVICE_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["is_valid"] is True

    # 3. Validate single trailer
    resp = await client.get(f"/internal/v1/trailers/{trailer_id}/validate", headers=SERVICE_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["is_valid"] is True

    # 4. Validate bulk
    resp = await client.post(
        "/internal/v1/assets/validate-bulk",
        json={"vehicle_ids": [vehicle_id, "NON_EXISTENT"], "trailer_ids": [trailer_id]},
        headers=SERVICE_HEADERS,
    )
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 3
    # Check that non-existent correctly mapped
    non_existent = next(r for r in results if r["asset_id"] == "NON_EXISTENT")
    assert non_existent["is_valid"] is False


@pytest.mark.asyncio
async def test_fuel_metadata_resolution(client: AsyncClient):
    # 1. Create setup
    create_hdrs = {**SERVICE_HEADERS, "X-Idempotency-Key": "fuel-test-01"}
    v_resp = await client.post(
        "/api/v1/vehicles",
        json={
            "asset_code": "V-FUEL-01",
            "plate": "34 FUEL 01",
            "ownership_type": "OWNED",
            "initial_spec": {"change_reason": "test info", "fuel_type": "DIESEL", "curb_weight_kg": 8000},
        },
        headers=create_hdrs,
    )
    vehicle_id = v_resp.json()["vehicle_id"]

    # 2. Resolve metadata
    resp = await client.post(
        "/internal/v1/assets/fuel-metadata/resolve", json={"vehicle_id": vehicle_id}, headers=SERVICE_HEADERS
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["vehicle_fuel_type"] == "DIESEL"
    assert data["combined_empty_weight_kg"] == 8000.0
