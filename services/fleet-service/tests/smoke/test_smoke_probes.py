import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_probes(client: AsyncClient):
    # Liveness
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # Readiness
    resp = await client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"
    assert resp.json()["checks"]["database"] == "ok"
    assert resp.json()["checks"]["broker"] == "ok"
    assert resp.json()["checks"]["outbox_relay"] == "ok"
    assert resp.json()["checks"]["worker"] == "ok"
    assert resp.json()["checks"]["auth_verify"] == "ok"
    assert resp.json()["checks"]["auth_outbound"] == "ok"


@pytest.mark.asyncio
async def test_ready_requires_live_auth_outbound(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    async def cold_outbound() -> str:
        return "fail"

    monkeypatch.setattr("fleet_service.routers.health.auth_outbound_status", cold_outbound)

    resp = await client.get("/ready")

    assert resp.status_code == 503
    assert resp.json()["status"] == "not_ready"
    assert resp.json()["checks"]["auth_outbound"] == "fail"


@pytest.mark.asyncio
async def test_ready_fails_when_auth_outbound_is_invalid(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    async def broken_outbound() -> str:
        return "fail"

    monkeypatch.setattr("fleet_service.routers.health.auth_outbound_status", broken_outbound)

    resp = await client.get("/ready")

    assert resp.status_code == 503
    assert resp.json()["status"] == "not_ready"
    assert resp.json()["checks"]["auth_outbound"] == "fail"


@pytest.mark.asyncio
async def test_health_endpoints_are_not_served_under_v1_prefix(client: AsyncClient):
    prefixed = await client.get("/v1/health")

    assert prefixed.status_code == 404
