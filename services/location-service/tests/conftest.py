"""Shared test fixtures for Location Service tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer

from location_service.config import settings
from location_service.database import get_db
from location_service.main import create_app
from location_service.models import Base
from location_service.provider_health import ProviderProbeResult, reset_provider_probe_cache
from location_service.worker_heartbeats import record_worker_heartbeat

_pg_url: str = ""
TEST_AUTH_SECRET = "location-service-test-secret-please-change-me-32b"
settings.environment = "test"
settings.auth_jwt_secret = TEST_AUTH_SECRET
settings.auth_jwt_algorithm = "HS256"
settings.mapbox_api_key = "test-mapbox-key"
settings.enable_ors_validation = False


def _token(payload: dict[str, str]) -> str:
    return jwt.encode(payload, settings.resolved_auth_jwt_secret, algorithm=settings.auth_jwt_algorithm)


def _bearer_headers(payload: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(payload)}"}


ADMIN_HEADERS: dict[str, str] = _bearer_headers({"sub": "admin-test-001", "role": "ADMIN"})
SUPER_ADMIN_HEADERS: dict[str, str] = _bearer_headers({"sub": "super-admin-001", "role": "SUPER_ADMIN"})
INTERNAL_SERVICE_HEADERS: dict[str, str] = _bearer_headers(
    {"sub": "trip-service", "role": "SERVICE", "service": "trip-service"}
)
FORBIDDEN_SERVICE_HEADERS: dict[str, str] = _bearer_headers(
    {"sub": "other-service", "role": "SERVICE", "service": "other-service"}
)
FORBIDDEN_USER_HEADERS: dict[str, str] = _bearer_headers({"sub": "driver-test-001", "role": "DRIVER"})


@pytest.fixture(scope="session", autouse=True)
def configure_test_settings() -> None:
    settings.environment = "test"
    settings.auth_jwt_secret = TEST_AUTH_SECRET
    settings.auth_jwt_algorithm = "HS256"
    settings.mapbox_api_key = "test-mapbox-key"
    settings.enable_ors_validation = False


@pytest.fixture(scope="session")
def postgres_container() -> str:
    """Start a PostgreSQL 16 container for the entire test session."""
    global _pg_url
    with PostgresContainer("postgres:16-alpine") as pg:
        url = pg.get_connection_url()
        _pg_url = url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
        _pg_url = _pg_url.replace("postgresql://", "postgresql+asyncpg://")
        settings.database_url = _pg_url
        yield _pg_url


@pytest_asyncio.fixture
async def db_engine(postgres_container: str):
    """Create a fresh engine and clean schema for each test."""
    engine = create_async_engine(_pg_url, echo=False, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def test_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a session for direct DB manipulation in tests."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        if session.in_transaction():
            try:
                await session.rollback()
            except Exception:
                pass


@pytest_asyncio.fixture(autouse=True)
async def reset_provider_probe() -> AsyncGenerator[None, None]:
    await reset_provider_probe_cache()
    yield
    await reset_provider_probe_cache()


@pytest_asyncio.fixture
async def raw_client(db_engine, monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[AsyncClient, None]:
    """Provide an unauthenticated test client for auth and health checks."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    app = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    monkeypatch.setattr("location_service.database.async_session_factory", session_factory)
    monkeypatch.setattr("location_service.routers.health.async_session_factory", session_factory)
    monkeypatch.setattr("location_service.processing.pipeline.async_session_factory", session_factory)
    monkeypatch.setattr("location_service.processing.approval.async_session_factory", session_factory)
    monkeypatch.setattr("location_service.processing.bulk.async_session_factory", session_factory)
    monkeypatch.setattr("location_service.processing.worker.async_session_factory", session_factory)
    monkeypatch.setattr("location_service.worker_heartbeats.async_session_factory", session_factory)
    await record_worker_heartbeat("processing-worker", datetime.now(UTC))

    async def healthy_probe() -> ProviderProbeResult:
        return ProviderProbeResult(
            mapbox_live="ok",
            ors_live="disabled" if not settings.enable_ors_validation else "ok",
            checked_at_utc=datetime.now(UTC),
        )

    monkeypatch.setattr("location_service.routers.health.get_provider_probe_result", healthy_probe)
    monkeypatch.setattr("location_service.routers.health.provider_probe_age_seconds", lambda _result: 0)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def client(raw_client: AsyncClient) -> AsyncGenerator[AsyncClient, None]:
    """Provide a public-admin authenticated test client."""
    raw_client.headers.update(ADMIN_HEADERS)
    yield raw_client


@pytest_asyncio.fixture
async def internal_client(raw_client: AsyncClient) -> AsyncGenerator[AsyncClient, None]:
    """Provide an internal trip-service authenticated test client."""
    raw_client.headers.update(INTERNAL_SERVICE_HEADERS)
    yield raw_client
