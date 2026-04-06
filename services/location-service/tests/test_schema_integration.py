from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from location_service.config import settings
from location_service.errors import unexpected_exception_handler
from location_service.main import create_app
from location_service.provider_health import ProviderProbeResult, get_provider_probe_result


@pytest.mark.asyncio
async def test_health_endpoint(raw_client: AsyncClient) -> None:
    response = await raw_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert (await raw_client.get("/api/v1/location/v1/health")).status_code == 404


@pytest.mark.asyncio
async def test_ready_endpoint(raw_client: AsyncClient) -> None:
    response = await raw_client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["checks"]["database"] == "ok"
    assert data["checks"]["mapbox"] == "ok"
    assert data["checks"]["mapbox_live"] == "ok"
    assert data["checks"]["auth_verify"] == "ok"
    assert data["checks"]["provider_probe_age_s"] == 0
    assert data["checks"]["processing_worker"] == "ok"
    assert (await raw_client.get("/api/v1/location/v1/ready")).status_code == 404


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_prometheus_payload(raw_client: AsyncClient) -> None:
    response = await raw_client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "location_api_requests_total" in response.text


@pytest.mark.asyncio
async def test_ready_returns_503_when_mapbox_key_missing(
    raw_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "mapbox_api_key", "")
    response = await raw_client.get("/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["mapbox"] == "missing"


@pytest.mark.asyncio
async def test_ready_returns_503_when_cached_provider_probe_is_unavailable(
    raw_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unhealthy_probe() -> ProviderProbeResult:
        return ProviderProbeResult(
            mapbox_live="unavailable",
            ors_live="disabled",
            checked_at_utc=datetime.now(UTC),
        )

    monkeypatch.setattr("location_service.routers.health.get_provider_probe_result", unhealthy_probe)
    monkeypatch.setattr("location_service.routers.health.provider_probe_age_seconds", lambda _result: 4)

    response = await raw_client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["mapbox_live"] == "unavailable"
    assert response.json()["checks"]["provider_probe_age_s"] == 4


@pytest.mark.asyncio
async def test_ready_returns_503_when_processing_worker_heartbeat_missing(
    raw_client: AsyncClient, test_session: AsyncSession
) -> None:
    await test_session.execute(text("DELETE FROM worker_heartbeats"))
    await test_session.commit()

    response = await raw_client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["processing_worker"] == "unavailable"


@pytest.mark.asyncio
async def test_provider_probe_result_uses_ttl_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    mapbox_calls = 0
    ors_calls = 0

    async def probe_mapbox() -> str:
        nonlocal mapbox_calls
        mapbox_calls += 1
        return "ok"

    async def probe_ors() -> str:
        nonlocal ors_calls
        ors_calls += 1
        return "disabled"

    monkeypatch.setattr(settings, "provider_probe_ttl_seconds", 30)
    monkeypatch.setattr("location_service.provider_health._probe_mapbox", probe_mapbox)
    monkeypatch.setattr("location_service.provider_health._probe_ors", probe_ors)

    first = await get_provider_probe_result()
    second = await get_provider_probe_result()

    assert first.mapbox_live == "ok"
    assert second.mapbox_live == "ok"
    assert mapbox_calls == 1
    assert ors_calls == 1


def test_docs_are_disabled_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "environment", "prod")
    monkeypatch.setattr(settings, "auth_jwt_algorithm", "RS256")
    monkeypatch.setattr(settings, "auth_issuer", "lojinext-platform")
    monkeypatch.setattr(settings, "auth_audience", "lojinext-platform")
    monkeypatch.setattr(settings, "auth_jwks_url", "http://identity-api:8105/.well-known/jwks.json")
    monkeypatch.setattr(settings, "database_url", "postgresql+asyncpg://user:pass@db.example.com:5432/location")
    monkeypatch.setattr(settings, "mapbox_api_key", "mapbox-key")
    monkeypatch.setattr(settings, "enable_ors_validation", False)

    app = create_app()

    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None


@pytest.mark.asyncio
async def test_unhandled_exception_returns_problem_json() -> None:
    app = FastAPI()
    app.add_exception_handler(Exception, unexpected_exception_handler)

    @app.get("/boom")
    async def boom() -> JSONResponse:
        raise RuntimeError("boom")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom")

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "LOCATION_INTERNAL_ERROR"


@pytest.mark.asyncio
async def test_ready_returns_503_when_jwks_is_unreachable(
    raw_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("location_service.routers.health.auth_verify_status", lambda: "fail")

    response = await raw_client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["auth_verify"] == "fail"


@pytest.mark.asyncio
async def test_ready_returns_503_when_jwks_is_malformed(
    raw_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("location_service.routers.health.auth_verify_status", lambda: "fail")

    response = await raw_client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["auth_verify"] == "fail"
