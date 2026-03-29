from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from location_service.config import settings
from location_service.errors import unexpected_exception_handler
from location_service.main import create_app


@pytest.mark.asyncio
async def test_health_endpoint(raw_client: AsyncClient) -> None:
    response = await raw_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_ready_endpoint(raw_client: AsyncClient) -> None:
    response = await raw_client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["checks"]["database"] == "ok"
    assert data["checks"]["mapbox"] == "ok"


@pytest.mark.asyncio
async def test_ready_returns_503_when_mapbox_key_missing(
    raw_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "mapbox_api_key", "")
    response = await raw_client.get("/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["mapbox"] == "missing"


def test_docs_are_disabled_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "environment", "prod")
    monkeypatch.setattr(settings, "auth_jwt_secret", "prod-secret-12345678901234567890")
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
