from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from fleet_service.domain.etag import generate_spec_etag
from tests.conftest import ADMIN_HEADERS, FORBIDDEN_SERVICE_HEADERS, SERVICE_HEADERS, SUPER_ADMIN_HEADERS


@pytest.mark.asyncio
async def test_internal_validate_endpoints(client: AsyncClient):
    create_hdrs = {**ADMIN_HEADERS, "Idempotency-Key": "internal-test-01"}
    v_resp = await client.post(
        "/api/v1/vehicles",
        json={"asset_code": "V-INT-01", "plate": "34 INT 01", "ownership_type": "OWNED"},
        headers=create_hdrs,
    )
    vehicle_id = v_resp.json()["vehicle_id"]

    t_hdrs = {**ADMIN_HEADERS, "Idempotency-Key": "internal-test-02"}
    t_resp = await client.post(
        "/api/v1/trailers",
        json={"asset_code": "T-INT-01", "plate": "34 INT 55", "ownership_type": "LEASED"},
        headers=t_hdrs,
    )
    trailer_id = t_resp.json()["trailer_id"]

    resp = await client.get(f"/internal/v1/vehicles/{vehicle_id}/validate", headers=SERVICE_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["exists"] is True

    resp = await client.get(f"/internal/v1/trailers/{trailer_id}/validate", headers=SERVICE_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["exists"] is True

    resp = await client.post(
        "/internal/v1/assets/validate-bulk",
        json={"vehicle_ids": [vehicle_id, "NON_EXISTENT"], "trailer_ids": [trailer_id]},
        headers=SERVICE_HEADERS,
    )
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 3
    non_existent = next(r for r in results if r["asset_id"] == "NON_EXISTENT")
    assert non_existent["exists"] is False

    compat = await client.post(
        "/internal/v1/trip-references/validate",
        json={"driver_id": "driver-001", "vehicle_id": vehicle_id, "trailer_id": trailer_id},
        headers=SERVICE_HEADERS,
    )
    compat_data = compat.json()
    assert compat.status_code == 200
    assert compat_data["valid"] is True
    assert compat_data["driver_valid"] is True
    assert compat_data["vehicle_valid"] is True
    assert compat_data["trailer_valid"] is True

    compat_nullable = await client.post(
        "/internal/v1/trip-references/validate",
        json={"driver_id": "driver-001", "vehicle_id": None, "trailer_id": None},
        headers=SERVICE_HEADERS,
    )
    compat_nullable_data = compat_nullable.json()
    assert compat_nullable.status_code == 200
    assert compat_nullable_data["driver_valid"] is True
    assert compat_nullable_data["vehicle_valid"] is None
    assert compat_nullable_data["trailer_valid"] is None


@pytest.mark.asyncio
async def test_internal_endpoints_reject_unknown_service_tokens(client: AsyncClient):
    response = await client.post(
        "/internal/v1/trip-references/validate",
        json={"driver_id": "driver-001", "vehicle_id": None, "trailer_id": None},
        headers=FORBIDDEN_SERVICE_HEADERS,
    )
    assert response.status_code == 403
    assert response.json()["code"] == "UNAUTHORIZED_INTERNAL_CALL"


@pytest.mark.asyncio
async def test_fuel_metadata_resolution(client: AsyncClient):
    create_hdrs = {**ADMIN_HEADERS, "Idempotency-Key": "fuel-test-01"}
    v_resp = await client.post(
        "/api/v1/vehicles",
        json={
            "asset_code": "V-FUEL-01",
            "plate": "34 FUEL 01",
            "ownership_type": "OWNED",
        },
        headers=create_hdrs,
    )
    vehicle_id = v_resp.json()["vehicle_id"]
    vehicle_spec_etag = generate_spec_etag("VEHICLE", vehicle_id, 0)

    spec_resp = await client.post(
        f"/api/v1/vehicles/{vehicle_id}/spec-versions",
        json={"change_reason": "test info", "fuel_type": "DIESEL", "curb_weight_kg": 8000},
        headers={**ADMIN_HEADERS, "If-Match": vehicle_spec_etag},
    )
    assert spec_resp.status_code == 201

    resp = await client.post(
        "/internal/v1/assets/fuel-metadata/resolve", json={"vehicle_id": vehicle_id}, headers=SERVICE_HEADERS
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["vehicle"]["fuel_type"] == "DIESEL"
    assert float(data["derived_combination"]["combined_empty_weight_kg"]) == 8000.0


@pytest.mark.asyncio
async def test_vehicle_hard_delete_invokes_trip_reference_check(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    create_resp = await client.post(
        "/api/v1/vehicles",
        json={"asset_code": "V-HARD-01", "plate": "34 HD 01", "ownership_type": "OWNED"},
        headers={**ADMIN_HEADERS, "Idempotency-Key": "hard-delete-contract-01"},
    )
    vehicle_id = create_resp.json()["vehicle_id"]
    etag = create_resp.headers["ETag"]

    soft_delete = await client.post(
        f"/api/v1/vehicles/{vehicle_id}/soft-delete",
        json={"reason": "contract test"},
        headers={**ADMIN_HEADERS, "If-Match": etag},
    )
    soft_delete_etag = soft_delete.headers["ETag"]

    checker = AsyncMock(
        return_value={
            "asset_id": vehicle_id,
            "asset_type": "VEHICLE",
            "is_referenced": False,
            "has_references": False,
            "active_trip_count": 0,
        }
    )
    monkeypatch.setattr("fleet_service.clients.trip_client.check_asset_references", checker)

    hard_delete = await client.post(
        f"/api/v1/vehicles/{vehicle_id}/hard-delete",
        json={"reason": "cleanup"},
        headers={**SUPER_ADMIN_HEADERS, "If-Match": soft_delete_etag},
    )

    assert hard_delete.status_code == 200
    checker.assert_awaited_once_with(vehicle_id, "VEHICLE")
