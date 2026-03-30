"""Smoke tests verifying critical paths across the Driver Service (spec §18)."""

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# SMOKE TESTS
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_lifecycle_smoke(client: AsyncClient, auth_admin: dict[str, str], monkeypatch):
    """Smoke Test: Create -> List -> Detail -> Update -> Inactivate -> Soft Delete -> Hard Delete."""
    from driver_service.config import settings

    monkeypatch.setattr(settings, "enable_hard_delete", True)

    from unittest.mock import patch

    import httpx

    mock_response = httpx.Response(
        200, json={"driver_id": "mock_id", "has_references": False, "safe_to_delete": True, "active_trip_count": 0}
    )

    # 1. Create Driver
    payload = {
        "full_name": "Smoke Test Driver",
        "phone": "+905556667788",
        "license_class": "C",
        "employment_start_date": "2024-01-01",
    }
    resp = await client.post("/api/v1/drivers", json=payload, headers=auth_admin)
    assert resp.status_code == 201
    driver_id = resp.json()["driver_id"]
    etag = resp.headers["ETag"]

    # 2. List Drivers (Verify it appears)
    list_resp = await client.get("/api/v1/drivers", headers=auth_admin)
    assert list_resp.status_code == 200
    assert any(d["driver_id"] == driver_id for d in list_resp.json()["items"])

    # 3. Get Detail
    detail_resp = await client.get(f"/api/v1/drivers/{driver_id}", headers=auth_admin)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["status"] == "ACTIVE"

    # 4. Update Driver
    upd_resp = await client.patch(
        f"/api/v1/drivers/{driver_id}", json={"note": "smoke update"}, headers={**auth_admin, "If-Match": etag}
    )
    assert upd_resp.status_code == 200
    etag = upd_resp.headers["ETag"]

    # 5. Inactivate Driver
    inact_resp = await client.post(
        f"/api/v1/drivers/{driver_id}/inactivate",
        json={"inactive_reason": "smoke test"},
        headers={**auth_admin, "If-Match": etag},
    )
    assert inact_resp.status_code == 200
    assert inact_resp.json()["status"] == "INACTIVE"
    etag = inact_resp.headers["ETag"]

    # 6. Soft Delete
    sd_resp = await client.post(
        f"/api/v1/drivers/{driver_id}/soft-delete",
        json={"reason": "cleaning up"},
        headers={**auth_admin, "If-Match": etag},
    )
    assert sd_resp.status_code == 200

    # 7. Verify Soft Deleted state
    del_detail_resp = await client.get(f"/api/v1/drivers/{driver_id}", headers=auth_admin)
    assert del_detail_resp.status_code == 200
    assert del_detail_resp.json()["lifecycle_state"] == "SOFT_DELETED"

    # 8. Hard Delete
    with patch("httpx.AsyncClient.get", return_value=mock_response):
        hd_resp = await client.post(f"/internal/v1/drivers/{driver_id}/hard-delete", headers=auth_admin)
        assert hd_resp.status_code == 200

    # 9. Verify Hard Deleted state -> 404
    final_resp = await client.get(f"/api/v1/drivers/{driver_id}", headers=auth_admin)
    assert final_resp.status_code == 404
