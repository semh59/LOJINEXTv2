"""Integration tests for Lifecycle endpoints (spec §18)."""

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# POST /api/v1/drivers/{id}/inactivate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inactivate_happy_path_and_idempotent(client: AsyncClient, auth_admin: dict[str, str]):
    """Inactivate happy path, reason required, double inactivate idempotent."""
    payload = {
        "full_name": "Inact Driver",
        "phone": "+905551110011",
        "license_class": "B",
        "employment_start_date": "2024-01-01",
    }
    create_resp = await client.post("/api/v1/drivers", json=payload, headers=auth_admin)
    data = create_resp.json()
    driver_id = data["driver_id"]
    etag = create_resp.headers["ETag"]

    # Inactivate
    req_body = {"inactive_reason": "On vacation", "employment_end_date": "2024-12-31"}
    resp = await client.post(
        f"/api/v1/drivers/{driver_id}/inactivate", json=req_body, headers={**auth_admin, "If-Match": etag}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "INACTIVE"
    assert data["lifecycle_state"] == "INACTIVE"
    assert data["inactive_reason"] == "On vacation"
    assert data["employment_end_date"] == "2024-12-31"

    # Double inactivate (idempotent, BR-08)
    new_etag = resp.headers["ETag"]
    resp2 = await client.post(
        f"/api/v1/drivers/{driver_id}/inactivate", json=req_body, headers={**auth_admin, "If-Match": new_etag}
    )
    assert resp2.status_code == 200
    assert resp2.json()["row_version"] == data["row_version"]  # Version should not increment


# ---------------------------------------------------------------------------
# POST /api/v1/drivers/{id}/reactivate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reactivate_from_inactive(client: AsyncClient, auth_admin: dict[str, str]):
    """Reactivate from INACTIVE (BR-10)."""
    payload = {
        "full_name": "Reactivate From Inact",
        "phone": "+905551110022",
        "license_class": "B",
        "employment_start_date": "2024-01-01",
    }
    create_resp = await client.post("/api/v1/drivers", json=payload, headers=auth_admin)
    driver_id = create_resp.json()["driver_id"]
    etag1 = create_resp.headers["ETag"]

    inact_resp = await client.post(
        f"/api/v1/drivers/{driver_id}/inactivate",
        json={"inactive_reason": "Temp"},
        headers={**auth_admin, "If-Match": etag1},
    )
    etag2 = inact_resp.headers["ETag"]

    # Reactivate
    resp = await client.post(f"/api/v1/drivers/{driver_id}/reactivate", headers={**auth_admin, "If-Match": etag2})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ACTIVE"
    assert data["lifecycle_state"] == "ACTIVE"
    assert data["inactive_reason"] is None


@pytest.mark.asyncio
async def test_reactivate_from_soft_deleted(client: AsyncClient, auth_admin: dict[str, str]):
    """Reactivate from SOFT_DELETED goes directly to ACTIVE (Architecture constraint)."""
    payload = {
        "full_name": "Reactivate From Soft",
        "phone": "+905551110033",
        "license_class": "B",
        "employment_start_date": "2024-01-01",
    }
    create_resp = await client.post("/api/v1/drivers", json=payload, headers=auth_admin)
    driver_id = create_resp.json()["driver_id"]
    etag1 = create_resp.headers["ETag"]

    # Soft Delete
    soft_resp = await client.post(
        f"/api/v1/drivers/{driver_id}/soft-delete",
        json={"reason": "Removed"},
        headers={**auth_admin, "If-Match": etag1},
    )
    etag2 = soft_resp.headers["ETag"]

    # Reactivate
    resp = await client.post(f"/api/v1/drivers/{driver_id}/reactivate", headers={**auth_admin, "If-Match": etag2})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ACTIVE"
    assert data["lifecycle_state"] == "ACTIVE"
    assert data["soft_deleted_at_utc"] is None
    assert data["soft_delete_reason"] is None


# ---------------------------------------------------------------------------
# POST /api/v1/drivers/{id}/soft-delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_soft_delete_happy_path(client: AsyncClient, auth_admin: dict[str, str]):
    """Soft delete happy path (BR-13) and fetch logic."""
    payload = {
        "full_name": "Soft Deleted Driver",
        "phone": "+905551110044",
        "license_class": "B",
        "employment_start_date": "2024-01-01",
    }
    create_resp = await client.post("/api/v1/drivers", json=payload, headers=auth_admin)
    driver_id = create_resp.json()["driver_id"]
    etag1 = create_resp.headers["ETag"]

    # Soft Delete
    resp = await client.post(
        f"/api/v1/drivers/{driver_id}/soft-delete",
        json={"reason": "Left company"},
        headers={**auth_admin, "If-Match": etag1},
    )
    assert resp.status_code == 200
    assert resp.json()["lifecycle_state"] == "SOFT_DELETED"
    assert resp.json()["soft_delete_reason"] == "Left company"
    etag2 = resp.headers["ETag"]

    # GET soft-deleted -> 200 + lifecycle=SOFT_DELETED
    get_resp = await client.get(f"/api/v1/drivers/{driver_id}", headers=auth_admin)
    assert get_resp.status_code == 200
    assert get_resp.json()["lifecycle_state"] == "SOFT_DELETED"

    # Soft deleting again -> idempotent return
    resp2 = await client.post(
        f"/api/v1/drivers/{driver_id}/soft-delete",
        json={"reason": "Left company"},
        headers={**auth_admin, "If-Match": etag2},
    )
    assert resp2.status_code == 200
    assert resp2.json()["lifecycle_state"] == "SOFT_DELETED"


# ---------------------------------------------------------------------------
# GET /api/v1/drivers/{id}/audit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_audit_trail(client: AsyncClient, auth_admin: dict[str, str]):
    """GET audit -> mutation trail verification."""
    payload = {
        "full_name": "Audit Tracked",
        "phone": "+905551110055",
        "license_class": "B",
        "employment_start_date": "2024-01-01",
    }
    # 1. Create
    create_resp = await client.post("/api/v1/drivers", json=payload, headers=auth_admin)
    driver_id = create_resp.json()["driver_id"]
    etag1 = create_resp.headers["ETag"]

    # 2. Inactivate
    inact_resp = await client.post(
        f"/api/v1/drivers/{driver_id}/inactivate",
        json={"inactive_reason": "Break"},
        headers={**auth_admin, "If-Match": etag1},
    )
    etag2 = inact_resp.headers["ETag"]

    # 3. Soft Delete
    await client.post(
        f"/api/v1/drivers/{driver_id}/soft-delete", json={"reason": "Gone"}, headers={**auth_admin, "If-Match": etag2}
    )

    # Fetch audit
    resp = await client.get(f"/api/v1/drivers/{driver_id}/audit", headers=auth_admin)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3

    actions = [item["action_type"] for item in data["items"]]
    assert actions == ["SOFT_DELETE", "STATUS_CHANGE", "CREATE"]  # Descending by created_at_utc
