"""Integration tests for Internal endpoints (spec §18)."""

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# GET /internal/v1/drivers/{id}/resolve
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_driver(client: AsyncClient, auth_internal: dict[str, str], auth_admin: dict[str, str]):
    """Internal resolve returns exact subset of fields (BR-15)."""
    # Create driver first via public API
    payload = {
        "full_name": "Resolve Target",
        "phone": "+905553331122",
        "telegram_user_id": "resolver_tg",
        "license_class": "CE",
        "employment_start_date": "2024-01-01",
    }
    create_resp = await client.post("/api/v1/drivers", json=payload, headers=auth_admin)
    driver_id = create_resp.json()["driver_id"]

    # Call resolve
    resp = await client.get(f"/internal/v1/drivers/{driver_id}/resolve", headers=auth_internal)
    assert resp.status_code == 200
    data = resp.json()

    # Verify exactly the fields expected
    assert set(data.keys()) == {
        "driver_id",
        "company_driver_code",
        "full_name",
        "phone_e164",
        "telegram_user_id",
        "license_class",
        "status",
        "lifecycle_state",
        "is_assignable",
    }
    assert "driver_id" in data
    assert data["driver_id"] == driver_id
    assert "status" in data
    assert data["telegram_user_id"] == "resolver_tg"

    # Should contain core data needed by other services
    assert "full_name" in data
    assert "phone_e164" in data
    assert data["phone_e164"] == "+905553331122"


@pytest.mark.asyncio
async def test_resolve_driver_not_found(client: AsyncClient, auth_internal: dict[str, str]):
    resp = await client.get("/internal/v1/drivers/01HZZZZZZZZZZZZZZZZZZZZZZZ/resolve", headers=auth_internal)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /internal/v1/drivers/lookup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lookup_driver_exact_match(
    client: AsyncClient, auth_internal: dict[str, str], auth_admin: dict[str, str]
):
    """Lookup by phone or telegram returns driver_id."""
    payload = {
        "full_name": "Lookup Target",
        "phone": "+905554445566",
        "telegram_user_id": "lookup_tg",
        "license_class": "B",
        "employment_start_date": "2024-01-01",
    }
    create_resp = await client.post("/api/v1/drivers", json=payload, headers=auth_admin)
    driver_id = create_resp.json()["driver_id"]

    # 1. Lookup by phone
    resp_phone = await client.get("/internal/v1/drivers/lookup?phone_e164=%2B905554445566", headers=auth_internal)
    assert resp_phone.status_code == 200
    assert resp_phone.json()["driver_id"] == driver_id

    # 2. Lookup by telegram
    resp_tg = await client.get("/internal/v1/drivers/lookup?telegram_user_id=lookup_tg", headers=auth_internal)
    assert resp_tg.status_code == 200
    assert resp_tg.json()["driver_id"] == driver_id

    # 3. Lookup both (invalid via BR-lookup)
    resp_both = await client.get(
        "/internal/v1/drivers/lookup?phone_e164=%2B905554445566&telegram_user_id=lookup_tg", headers=auth_internal
    )
    assert resp_both.status_code == 422
    assert resp_both.json()["code"] == "DRIVER_LOOKUP_MODE_INVALID"


# ---------------------------------------------------------------------------
# POST /internal/v1/drivers/eligibility/check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_eligibility_check_success(
    client: AsyncClient, auth_internal: dict[str, str], auth_admin: dict[str, str]
):
    """Eligibility bulk check for assignment."""
    # Create an active and an inactive driver
    d1 = (
        await client.post(
            "/api/v1/drivers",
            json={
                "full_name": "Active",
                "phone": "+905556667788",
                "license_class": "C",
                "employment_start_date": "2024-01-01",
            },
            headers=auth_admin,
        )
    ).json()["driver_id"]

    act_resp = await client.post(
        "/api/v1/drivers",
        json={
            "full_name": "Inact",
            "phone": "+905556667799",
            "license_class": "B",
            "employment_start_date": "2024-01-01",
        },
        headers=auth_admin,
    )
    d2 = act_resp.json()["driver_id"]
    etag2 = act_resp.headers["ETag"]

    await client.post(
        f"/api/v1/drivers/{d2}/inactivate", json={"inactive_reason": "off"}, headers={**auth_admin, "If-Match": etag2}
    )

    # Unknown ID
    d3 = "01HZZZZZZZZZZZZZZZZZZZZZZZ"

    # Check eligibility
    resp = await client.post(
        "/internal/v1/drivers/eligibility/check", json={"driver_ids": [d1, d2, d3]}, headers=auth_internal
    )
    assert resp.status_code == 200
    data = resp.json()
    items = data["items"]

    d1_res = next(i for i in items if i["driver_id"] == d1)
    d2_res = next(i for i in items if i["driver_id"] == d2)
    d3_res = next(i for i in items if i["driver_id"] == d3)

    assert d1_res["exists"] is True
    assert d1_res["status"] == "ACTIVE"
    assert d1_res["is_assignable"] is True

    assert d2_res["exists"] is True
    assert d2_res["status"] == "INACTIVE"
    assert d2_res["is_assignable"] is False

    assert d3_res["exists"] is False


@pytest.mark.asyncio
async def test_eligibility_check_limit(client: AsyncClient, auth_internal: dict[str, str]):
    """Max 200 IDs allowed."""
    ids = ["01HZZZZZZZZZZZZZZZZZZZZZZZ"] * 201
    resp = await client.post("/internal/v1/drivers/eligibility/check", json={"driver_ids": ids}, headers=auth_internal)
    assert resp.status_code == 422
