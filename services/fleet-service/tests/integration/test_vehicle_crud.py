import pytest
from httpx import AsyncClient

from tests.conftest import ADMIN_HEADERS, SUPER_ADMIN_HEADERS


@pytest.mark.asyncio
async def test_vehicle_full_crud_lifecycle(client: AsyncClient):
    # 1. Create Vehicle
    create_payload = {
        "asset_code": "V-101",
        "plate": "34 ABC 123",
        "ownership_type": "OWNED",
        "brand": "Mercedes-Benz",
        "model": "Actros",
        "model_year": 2023,
        "notes": "Initial test vehicle",
    }

    # Missing idempotency key should fail (400)
    resp = await client.post("/api/v1/vehicles", json=create_payload, headers=ADMIN_HEADERS)
    assert resp.status_code == 400
    assert "Idempotency-Key" in resp.text

    # Successful create
    headers = {**ADMIN_HEADERS, "Idempotency-Key": "idem-001"}
    resp = await client.post("/api/v1/vehicles", json=create_payload, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    vehicle_id = data["vehicle_id"]
    etag = resp.headers["ETag"]
    assert data["normalized_plate_current"] == "34ABC123"
    assert data["status"] == "ACTIVE"

    # 2. Idempotency Replay
    resp_replay = await client.post("/api/v1/vehicles", json=create_payload, headers=headers)
    assert resp_replay.status_code == 201
    assert resp_replay.json()["vehicle_id"] == vehicle_id

    # 3. GET Detail
    resp = await client.get(f"/api/v1/vehicles/{vehicle_id}", headers=ADMIN_HEADERS)
    assert resp.status_code == 200
    assert resp.headers["ETag"] == etag

    # 4. PATCH (Update brand and plate)
    patch_payload = {"brand": "Volvo", "plate": "34 XYZ 99"}

    # Missing If-Match fails closed under the current contract
    resp = await client.patch(f"/api/v1/vehicles/{vehicle_id}", json=patch_payload, headers=ADMIN_HEADERS)
    assert resp.status_code == 400

    # Wrong If-Match (412 Precondition Failed)
    resp = await client.patch(
        f"/api/v1/vehicles/{vehicle_id}", json=patch_payload, headers={**ADMIN_HEADERS, "If-Match": 'W/"wrong"'}
    )
    assert resp.status_code == 412

    # Success PATCH
    resp = await client.patch(
        f"/api/v1/vehicles/{vehicle_id}", json=patch_payload, headers={**ADMIN_HEADERS, "If-Match": etag}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["brand"] == "Volvo"
    assert data["normalized_plate_current"] == "34XYZ99"
    new_etag = resp.headers["ETag"]
    assert new_etag != etag

    # 5. Deactivate
    resp = await client.post(
        f"/api/v1/vehicles/{vehicle_id}/deactivate",
        json={"reason": "Maintenance"},
        headers={**ADMIN_HEADERS, "If-Match": new_etag},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "INACTIVE"
    deact_etag = resp.headers["ETag"]

    # 6. Soft Delete
    resp = await client.post(
        f"/api/v1/vehicles/{vehicle_id}/soft-delete",
        json={"reason": "Retiring"},
        headers={**ADMIN_HEADERS, "If-Match": deact_etag},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["lifecycle_state"] == "SOFT_DELETED"
    soft_etag = resp.headers["ETag"]

    # 7. Hard Delete (Requires SUPER_ADMIN)
    # Admin attempt (403 Forbidden - handled by dependency)
    # Note: Our conftest ADMIN_HEADERS has role: ADMIN
    resp = await client.post(
        f"/api/v1/vehicles/{vehicle_id}/hard-delete",
        json={"reason": "Data correction"},
        headers={**ADMIN_HEADERS, "If-Match": soft_etag},
    )
    assert resp.status_code == 403

    # Super Admin attempt
    resp = await client.post(
        f"/api/v1/vehicles/{vehicle_id}/hard-delete",
        json={"reason": "Data correction"},
        headers={**SUPER_ADMIN_HEADERS, "If-Match": soft_etag},
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    # 8. Verify Gone
    resp = await client.get(f"/api/v1/vehicles/{vehicle_id}", headers=ADMIN_HEADERS)
    assert resp.status_code == 404
