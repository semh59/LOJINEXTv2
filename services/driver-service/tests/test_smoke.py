"""Smoke tests verifying critical paths across the Driver Service (spec section 18)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

import driver_service.database as driver_database
from driver_service.main import app
from driver_service.models import DriverModel
from driver_service.worker_heartbeats import record_worker_heartbeat


@pytest.mark.asyncio
async def test_full_lifecycle_smoke(
    client: AsyncClient, auth_admin: dict[str, str], auth_internal: dict[str, str], monkeypatch
):
    """Smoke test: create -> list -> detail -> update -> inactivate -> soft delete -> hard delete."""
    from driver_service.config import settings

    monkeypatch.setattr(settings, "enable_hard_delete", True)

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

    list_resp = await client.get("/api/v1/drivers", headers=auth_admin)
    assert list_resp.status_code == 200
    assert any(d["driver_id"] == driver_id for d in list_resp.json()["items"])

    detail_resp = await client.get(f"/api/v1/drivers/{driver_id}", headers=auth_admin)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["status"] == "ACTIVE"

    upd_resp = await client.patch(
        f"/api/v1/drivers/{driver_id}", json={"note": "smoke update"}, headers={**auth_admin, "If-Match": etag}
    )
    assert upd_resp.status_code == 200
    etag = upd_resp.headers["ETag"]

    inact_resp = await client.post(
        f"/api/v1/drivers/{driver_id}/inactivate",
        json={"inactive_reason": "smoke test"},
        headers={**auth_admin, "If-Match": etag},
    )
    assert inact_resp.status_code == 200
    assert inact_resp.json()["status"] == "INACTIVE"
    etag = inact_resp.headers["ETag"]

    sd_resp = await client.post(
        f"/api/v1/drivers/{driver_id}/soft-delete",
        json={"reason": "cleaning up"},
        headers={**auth_admin, "If-Match": etag},
    )
    assert sd_resp.status_code == 200

    del_detail_resp = await client.get(f"/api/v1/drivers/{driver_id}", headers=auth_admin)
    assert del_detail_resp.status_code == 200
    assert del_detail_resp.json()["lifecycle_state"] == "SOFT_DELETED"

    async def mock_trip_check(*_args, **_kwargs):
        return True

    monkeypatch.setattr("driver_service.routers.maintenance._check_trip_references", mock_trip_check)

    hd_resp = await client.post(f"/internal/v1/drivers/{driver_id}/hard-delete", headers=auth_internal)
    assert hd_resp.status_code == 200
    assert hd_resp.json()["status"] == "HARD_DELETED"

    async with driver_database.async_session_factory() as session:
        remaining_driver = (
            await session.execute(select(DriverModel.driver_id).where(DriverModel.driver_id == driver_id))
        ).scalar_one_or_none()
    assert remaining_driver is None


@pytest.mark.asyncio
async def test_ready_returns_503_when_worker_heartbeats_missing(client: AsyncClient):
    """Readiness must fail when required workers have not reported heartbeats."""
    response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"]["auth_verify"] == "ok"
    assert response.json()["checks"]["auth_outbound"] == "ok"
    assert response.json()["checks"]["broker"] == "ok"
    assert response.json()["checks"]["outbox_relay"] == "missing"
    assert response.json()["checks"]["import_worker"] == "missing"


@pytest.mark.asyncio
async def test_ready_returns_200_when_worker_heartbeats_are_fresh(client: AsyncClient):
    """Readiness returns 200 only when required worker heartbeats are fresh."""
    async with driver_database.async_session_factory() as session:
        await record_worker_heartbeat(session, "outbox_relay", status="RUNNING")
        await record_worker_heartbeat(session, "import_worker", status="RUNNING")
        await session.commit()

    response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["checks"]["auth_verify"] == "ok"
    assert response.json()["checks"]["auth_outbound"] == "ok"
    assert response.json()["checks"]["broker"] == "ok"
    assert response.json()["checks"]["outbox_relay"] == "ok"
    assert response.json()["checks"]["import_worker"] == "ok"


@pytest.mark.asyncio
async def test_ready_returns_503_when_broker_missing(client: AsyncClient):
    """Readiness must fail when the app broker is not wired."""
    async with driver_database.async_session_factory() as session:
        await record_worker_heartbeat(session, "outbox_relay", status="RUNNING")
        await record_worker_heartbeat(session, "import_worker", status="RUNNING")
        await session.commit()

    delattr(app.state, "broker")

    response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"]["auth_verify"] == "ok"
    assert response.json()["checks"]["auth_outbound"] == "ok"
    assert response.json()["checks"]["broker"] == "missing"
    assert response.json()["checks"]["database"] == "ok"


@pytest.mark.asyncio
async def test_ready_allows_cold_outbound_auth(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Readiness stays green when outbound auth is cold but correctly configured."""
    async with driver_database.async_session_factory() as session:
        await record_worker_heartbeat(session, "outbox_relay", status="RUNNING")
        await record_worker_heartbeat(session, "import_worker", status="RUNNING")
        await session.commit()

    monkeypatch.setattr("driver_service.routers.auth_outbound_status", lambda: "cold")

    response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["checks"]["auth_outbound"] == "cold"


@pytest.mark.asyncio
async def test_ready_fails_when_outbound_auth_is_invalid(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Readiness fails when outbound auth config is invalid."""
    async with driver_database.async_session_factory() as session:
        await record_worker_heartbeat(session, "outbox_relay", status="RUNNING")
        await record_worker_heartbeat(session, "import_worker", status="RUNNING")
        await session.commit()

    monkeypatch.setattr("driver_service.routers.auth_outbound_status", lambda: "fail")

    response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"]["auth_outbound"] == "fail"
