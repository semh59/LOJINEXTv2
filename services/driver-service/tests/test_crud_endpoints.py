"""Integration tests for Core CRUD endpoints (spec §18)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from driver_service.models import DriverAuditLogModel, DriverModel, DriverOutboxModel

# ---------------------------------------------------------------------------
# POST /api/v1/drivers (Create)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_driver_happy_path(client: AsyncClient, auth_admin: dict[str, str], db_session: AsyncSession):
    """POST create happy path (BR-01, BR-06)."""
    payload = {
        "company_driver_code": "DRV-100",
        "full_name": "Ahmet Yılmaz",
        "phone": "0555 123 45 67",
        "telegram_user_id": "ahmet_tg",
        "license_class": "C, CE",
        "employment_start_date": "2024-01-01",
    }

    resp = await client.post("/api/v1/drivers", json=payload, headers=auth_admin)
    assert resp.status_code == 201, resp.text

    data = resp.json()
    assert data["driver_id"] is not None
    assert data["full_name"] == "Ahmet Yılmaz"
    assert data["phone"] == "+905551234567"
    assert data["phone_normalization_status"] == "NORMALIZED"
    assert data["status"] == "ACTIVE"
    assert data["lifecycle_state"] == "ACTIVE"
    assert data["is_assignable"] is True
    assert "ETag" in resp.headers

    # Verify DB state
    driver_id = data["driver_id"]
    driver = (await db_session.execute(select(DriverModel).where(DriverModel.driver_id == driver_id))).scalar_one()
    assert driver.full_name_search_key == "ahmet yilmaz"

    # Verify audit log
    audit = (
        await db_session.execute(select(DriverAuditLogModel).where(DriverAuditLogModel.driver_id == driver_id))
    ).scalar_one()
    assert audit.action_type == "CREATE"

    # Verify outbox event
    outbox = (
        await db_session.execute(select(DriverOutboxModel).where(DriverOutboxModel.driver_id == driver_id))
    ).scalar_one()
    assert outbox.event_name == "driver.created.v1"


@pytest.mark.asyncio
async def test_create_duplicate_phone(client: AsyncClient, auth_admin: dict[str, str]):
    """POST create duplicate phone → 409 (BR-03)."""
    payload = {
        "full_name": "First Driver",
        "phone": "5551112233",
        "license_class": "B",
        "employment_start_date": "2024-01-01",
    }
    await client.post("/api/v1/drivers", json=payload, headers=auth_admin)

    # Second driver with same phone
    payload2 = {
        "full_name": "Second Driver",
        "phone": "+905551112233",  # Same after normalization
        "license_class": "C",
        "employment_start_date": "2024-02-01",
    }
    resp = await client.post("/api/v1/drivers", json=payload2, headers=auth_admin)
    assert resp.status_code == 409
    assert resp.json()["code"] == "DRIVER_PHONE_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_create_duplicate_telegram(client: AsyncClient, auth_admin: dict[str, str]):
    """POST create duplicate telegram → 409 (BR-04)."""
    payload = {
        "full_name": "First Driver",
        "phone": "5552223344",
        "telegram_user_id": "shared_tg",
        "license_class": "B",
        "employment_start_date": "2024-01-01",
    }
    await client.post("/api/v1/drivers", json=payload, headers=auth_admin)

    payload2 = {
        "full_name": "Second Driver",
        "phone": "5552223355",
        "telegram_user_id": "shared_tg",
        "license_class": "C",
        "employment_start_date": "2024-02-01",
    }
    resp = await client.post("/api/v1/drivers", json=payload2, headers=auth_admin)
    assert resp.status_code == 409
    assert resp.json()["code"] == "DRIVER_TELEGRAM_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_create_bad_phone_normalization(client: AsyncClient, auth_admin: dict[str, str]):
    """POST create invalid phone → 422 (BR-01 manual create requirement)."""
    payload = {
        "full_name": "Bad Phone",
        "phone": "123",
        "license_class": "B",
        "employment_start_date": "2024-01-01",
    }
    resp = await client.post("/api/v1/drivers", json=payload, headers=auth_admin)
    assert resp.status_code == 422
    assert resp.json()["code"] == "DRIVER_VALIDATION_ERROR"
    assert "field" in resp.json()["errors"][0]


# ---------------------------------------------------------------------------
# GET /api/v1/drivers/{id} (Detail)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_detail_returns_etag_and_role_visibility(
    client: AsyncClient, auth_admin: dict[str, str], auth_manager: dict[str, str]
):
    """GET detail returns ETag and respects BR-16/BR-17 for managers."""
    payload = {
        "full_name": "Detail Driver",
        "phone": "05559998877",
        "license_class": "B",
        "employment_start_date": "2024-01-01",
        "note": "Secret admin note",
    }
    create_resp = await client.post("/api/v1/drivers", json=payload, headers=auth_admin)
    driver_id = create_resp.json()["driver_id"]
    etag = create_resp.headers["ETag"]

    # Admin fetch
    admin_resp = await client.get(f"/api/v1/drivers/{driver_id}", headers=auth_admin)
    assert admin_resp.status_code == 200
    assert admin_resp.headers["ETag"] == etag
    admin_data = admin_resp.json()
    assert admin_data["phone"] == "+905559998877"
    assert admin_data["note"] == "Secret admin note"

    # Manager fetch
    manager_resp = await client.get(f"/api/v1/drivers/{driver_id}", headers=auth_manager)
    assert manager_resp.status_code == 200
    manager_data = manager_resp.json()
    assert manager_data["phone"] == "+9055******77"  # Masked (BR-17)
    assert "note" not in manager_data  # Hidden (BR-16)


# ---------------------------------------------------------------------------
# GET /api/v1/drivers (List)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_default_active_only(client: AsyncClient, auth_admin: dict[str, str]):
    """GET list default active-only (BR-06 implementation check)."""
    # Create an ACTIVE driver
    await client.post(
        "/api/v1/drivers",
        json={
            "full_name": "Active One",
            "phone": "5550001122",
            "license_class": "B",
            "employment_start_date": "2024-01-01",
        },
        headers=auth_admin,
    )

    # List
    resp = await client.get("/api/v1/drivers", headers=auth_admin)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(d["full_name"] == "Active One" for d in data["items"])


# ---------------------------------------------------------------------------
# PATCH /api/v1/drivers/{id} (Update)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_stale_etag(client: AsyncClient, auth_admin: dict[str, str]):
    """PATCH stale ETag → 412 (Concurrency control)."""
    payload = {
        "full_name": "Patch Driver",
        "phone": "05551112233",
        "license_class": "B",
        "employment_start_date": "2024-01-01",
    }
    create_resp = await client.post("/api/v1/drivers", json=payload, headers=auth_admin)
    assert create_resp.status_code == 201, create_resp.text
    driver_id = create_resp.json()["driver_id"]
    etag = create_resp.headers["ETag"]

    # First PATCH (success)
    patch1 = await client.patch(
        f"/api/v1/drivers/{driver_id}", json={"license_class": "C"}, headers={**auth_admin, "If-Match": etag}
    )
    assert patch1.status_code == 200
    new_etag = patch1.headers["ETag"]
    assert new_etag != etag

    # Second PATCH with old ETag (fails)
    patch2 = await client.patch(
        f"/api/v1/drivers/{driver_id}", json={"license_class": "CE"}, headers={**auth_admin, "If-Match": etag}
    )
    assert patch2.status_code == 412
    assert patch2.json()["code"] == "DRIVER_VERSION_MISMATCH"


@pytest.mark.asyncio
async def test_patch_without_if_match(client: AsyncClient, auth_admin: dict[str, str]):
    """PATCH without If-Match header → 428 Precondition Required."""
    payload = {
        "full_name": "No ETag Driver",
        "phone": "5559990011",
        "license_class": "B",
        "employment_start_date": "2024-01-01",
    }
    create_resp = await client.post("/api/v1/drivers", json=payload, headers=auth_admin)
    driver_id = create_resp.json()["driver_id"]

    resp = await client.patch(f"/api/v1/drivers/{driver_id}", json={"license_class": "C"}, headers=auth_admin)
    assert resp.status_code == 428
    assert resp.json()["code"] == "DRIVER_IF_MATCH_REQUIRED"
