"""Edge cases based on spec §18."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from driver_service.models import DriverOutboxModel

# ---------------------------------------------------------------------------
# EDGE CASES
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_employment_end_date_only(client: AsyncClient, auth_admin: dict[str, str]):
    """Edge Case 28: Patch: employment_end_date only, status unchanged."""
    payload = {
        "full_name": "Edge Patch End Date",
        "phone": "+905558889900",
        "license_class": "B",
        "employment_start_date": "2024-01-01",
    }
    resp = await client.post("/api/v1/drivers", json=payload, headers=auth_admin)
    driver_id = resp.json()["driver_id"]
    etag = resp.headers["ETag"]

    # Patch only employment_end_date
    patch_resp = await client.patch(
        f"/api/v1/drivers/{driver_id}",
        json={"employment_end_date": "2024-12-31"},
        headers={**auth_admin, "If-Match": etag},
    )
    assert patch_resp.status_code == 200

    data = patch_resp.json()
    assert data["employment_end_date"] == "2024-12-31"
    assert data["status"] == "ACTIVE"  # Spec explicitly says rule BR-09: End date does NOT implicitly change status.


@pytest.mark.asyncio
async def test_reactivate_conflict(client: AsyncClient, auth_admin: dict[str, str]):
    """Edge Case 29: Reactivate: phone conflict -> 409."""
    # Create driver A
    payload_a = {
        "full_name": "Driver A",
        "phone": "+905558889911",
        "license_class": "B",
        "employment_start_date": "2024-01-01",
    }
    resp_a = await client.post("/api/v1/drivers", json=payload_a, headers=auth_admin)
    driver_id_a = resp_a.json()["driver_id"]
    etag_a = resp_a.headers["ETag"]

    # Soft delete A
    d_resp = await client.post(
        f"/api/v1/drivers/{driver_id_a}/soft-delete", json={"reason": "bye"}, headers={**auth_admin, "If-Match": etag_a}
    )
    assert d_resp.status_code == 200
    etag_a = d_resp.headers["ETag"]

    # Create driver B with same phone
    payload_b = {
        "full_name": "Driver B",
        "phone": "+905558889911",  # Same phone
        "license_class": "C",
        "employment_start_date": "2024-01-01",
    }
    resp_b = await client.post("/api/v1/drivers", json=payload_b, headers=auth_admin)
    assert resp_b.status_code == 201

    # Try Reactivate A (Conflict!)
    react_resp = await client.post(
        f"/api/v1/drivers/{driver_id_a}/reactivate", headers={**auth_admin, "If-Match": etag_a}
    )
    assert react_resp.status_code == 409
    assert react_resp.json()["code"] == "DRIVER_PHONE_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_hard_delete_blocked(
    client: AsyncClient, auth_admin: dict[str, str], auth_internal: dict[str, str], monkeypatch
):
    """Edge Case 31: Hard delete blocked by trips."""
    from unittest.mock import patch

    import httpx

    from driver_service.config import settings

    monkeypatch.setattr(settings, "enable_hard_delete", True)

    # Create
    resp = await client.post(
        "/api/v1/drivers",
        json={
            "full_name": "HD Target",
            "phone": "+905558889922",
            "license_class": "B",
            "employment_start_date": "2024-01-01",
        },
        headers=auth_admin,
    )
    driver_id = resp.json()["driver_id"]
    etag = resp.headers["ETag"]

    # Soft delete
    await client.post(
        f"/api/v1/drivers/{driver_id}/soft-delete", json={"reason": "bye"}, headers={**auth_admin, "If-Match": etag}
    )

    # Mock Trip Service as NOT safe to delete
    mock_response = httpx.Response(
        200, json={"driver_id": driver_id, "has_references": True, "safe_to_delete": False, "active_trip_count": 1}
    )

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        # Attempt hard delete
        hd_resp = await client.post(f"/internal/v1/drivers/{driver_id}/hard-delete", headers=auth_internal)

    assert hd_resp.status_code == 409
    assert hd_resp.json()["code"] == "DRIVER_HARD_DELETE_BLOCKED_BY_HISTORY"


@pytest.mark.asyncio
async def test_merge_disabled_by_flag(
    client: AsyncClient, auth_admin: dict[str, str], auth_internal: dict[str, str], monkeypatch
):
    """Edge Case 32: Merge disabled -> error."""
    # Disable via env
    monkeypatch.setenv("ENABLE_MERGE_ENDPOINT", "false")
    # Need to reload config slightly or we can just patch settings structure if imported
    from driver_service.config import settings

    monkeypatch.setattr(settings, "enable_merge_endpoint", False)

    resp = await client.post(
        "/internal/v1/drivers/merge",
        json={"source_driver_id": "A", "target_driver_id": "B", "reason": "test"},
        headers=auth_internal,
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "DRIVER_FORBIDDEN"


# Next: 33, 34 for telegram_changed
@pytest.mark.asyncio
async def test_telegram_changed_events(client: AsyncClient, auth_admin: dict[str, str], db_session):
    """Edge Case 33 & 34: telegram_changed on null->value and value->null."""
    resp = await client.post(
        "/api/v1/drivers",
        json={
            "full_name": "TG Edge Driver",
            "phone": "+905558889933",
            "license_class": "B",
            "employment_start_date": "2024-01-01",
        },
        headers=auth_admin,
    )
    driver_id = resp.json()["driver_id"]
    etag = resp.headers["ETag"]

    # 33. null -> val
    p_resp = await client.patch(
        f"/api/v1/drivers/{driver_id}", json={"telegram_user_id": "new_tg"}, headers={**auth_admin, "If-Match": etag}
    )
    etag = p_resp.headers["ETag"]

    # Check outbox event
    query = (
        select(DriverOutboxModel)
        .where(DriverOutboxModel.driver_id == driver_id, DriverOutboxModel.event_name == "driver.telegram_changed.v1")
        .order_by(DriverOutboxModel.created_at_utc.desc())
    )
    ev1 = (await db_session.execute(query)).scalars().first()
    assert ev1 is not None
    import json

    data1 = json.loads(ev1.payload_json)
    assert data1["old_telegram_user_id"] is None
    assert data1["new_telegram_user_id"] == "new_tg"

    # 34. val -> null
    await client.patch(
        f"/api/v1/drivers/{driver_id}", json={"telegram_user_id": None}, headers={**auth_admin, "If-Match": etag}
    )

    # Check outbox event (newest)
    ev2 = (await db_session.execute(query)).scalars().first()
    data2 = json.loads(ev2.payload_json)
    assert data2["old_telegram_user_id"] == "new_tg"
    assert data2["new_telegram_user_id"] is None
