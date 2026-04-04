import pytest
from httpx import AsyncClient

from tests.conftest import ADMIN_HEADERS


@pytest.mark.asyncio
async def test_optimistic_locking_master_etag_mismatch(client: AsyncClient):
    # 1. Create
    headers = {**ADMIN_HEADERS, "X-Idempotency-Key": "conc-test-01"}
    resp = await client.post(
        "/api/v1/vehicles",
        json={"asset_code": "V-CONC-01", "plate": "34 CONC 01", "ownership_type": "OWNED"},
        headers=headers,
    )
    vehicle_id = resp.json()["vehicle_id"]
    etag_v1 = resp.headers["ETag"]

    # 2. Competitor A updates (Success)
    await client.patch(
        f"/api/v1/vehicles/{vehicle_id}", json={"brand": "Brand A"}, headers={**ADMIN_HEADERS, "If-Match": etag_v1}
    )

    # 3. Competitor B tries to update using STALE etag_v1 (Fail 412)
    resp_b = await client.patch(
        f"/api/v1/vehicles/{vehicle_id}", json={"brand": "Brand B"}, headers={**ADMIN_HEADERS, "If-Match": etag_v1}
    )
    assert resp_b.status_code == 412
    assert "mismatch" in resp_b.text.lower()


@pytest.mark.asyncio
async def test_spec_stream_concurrency_mismatch(client: AsyncClient):
    # 1. Create with initial spec
    headers = {**ADMIN_HEADERS, "X-Idempotency-Key": "conc-test-02"}
    resp = await client.post(
        "/api/v1/vehicles",
        json={
            "asset_code": "V-CONC-02",
            "plate": "34 CONC 02",
            "ownership_type": "OWNED",
            "initial_spec": {"change_reason": "v1", "gvwr_kg": 10000},
        },
        headers=headers,
    )
    vehicle_id = resp.json()["vehicle_id"]
    spec_etag_v1 = resp.headers["X-Spec-ETag"]  # sv0

    # 2. Update Spec (Success sv0 -> sv1)
    resp_a = await client.post(
        f"/api/v1/vehicles/{vehicle_id}/specs",
        json={"change_reason": "v2 update", "gvwr_kg": 11000},
        headers={**ADMIN_HEADERS, "If-Match": spec_etag_v1},
    )
    assert resp_a.status_code == 201

    # 3. Try to use STALE spec_etag_v1 again (Fail 409/412 — spec service uses 409 for concurrency)
    # Check spec_service.py: raise SpecEtagMismatchError() -> 412
    resp_b = await client.post(
        f"/api/v1/vehicles/{vehicle_id}/specs",
        json={"change_reason": "v2 duplicate", "gvwr_kg": 12000},
        headers={**ADMIN_HEADERS, "If-Match": spec_etag_v1},
    )
    assert resp_b.status_code == 412
