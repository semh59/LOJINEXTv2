"""Shared test fixtures for Fleet Service tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from platform_auth_testing import build_test_jwks_bundle, install_jwks_urlopen_mock, sign_test_token
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer

import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from alembic import command
from fleet_service.broker import NoOpBroker
from fleet_service.config import settings
from fleet_service.database import get_session
import httpx
import respx


TEST_JWKS_BUNDLE = build_test_jwks_bundle()
settings.auth_issuer = TEST_JWKS_BUNDLE.issuer
settings.auth_audience = TEST_JWKS_BUNDLE.audience
settings.auth_jwks_url = TEST_JWKS_BUNDLE.jwks_url
from fleet_service.worker_heartbeats import record_worker_heartbeat

TRUNCATE_TABLES = (
    "fleet_vehicles",
    "fleet_vehicle_spec_versions",
    "fleet_trailers",
    "fleet_trailer_spec_versions",
    "fleet_asset_timeline_events",
    "fleet_asset_delete_audit",
    "fleet_outbox",
    "fleet_idempotency_records",
    "fleet_worker_heartbeats",
)

_pg_url: str = ""
TEST_JWKS_BUNDLE = build_test_jwks_bundle()
settings.environment = "test"
settings.auth_jwt_algorithm = "RS256"
settings.auth_issuer = TEST_JWKS_BUNDLE.issuer
settings.auth_audience = TEST_JWKS_BUNDLE.audience
settings.auth_jwks_url = TEST_JWKS_BUNDLE.jwks_url
settings.auth_service_token_url = "http://identity.test/auth/v1/token/service"
settings.auth_service_client_id = settings.service_name
settings.auth_service_client_secret = "fleet-client-secret"


def _token(payload: dict[str, Any]) -> str:
    """Build a JWT token for tests."""
    return sign_test_token(
        TEST_JWKS_BUNDLE,
        sub=str(payload["sub"]),
        role=str(payload["role"]),
        service=str(payload["service"]) if payload.get("service") is not None else None,
    )


def _bearer_headers(payload: dict[str, Any]) -> dict[str, str]:
    """Return an Authorization header for the given claims."""
    return {"Authorization": f"Bearer {_token(payload)}"}


ADMIN_HEADERS = _bearer_headers({"sub": "admin-test-001", "role": "MANAGER"})
SUPER_ADMIN_HEADERS = _bearer_headers({"sub": "super-admin-001", "role": "SUPER_ADMIN"})
SERVICE_HEADERS = _bearer_headers({"sub": "trip-service", "role": "SERVICE", "service": "trip-service"})
FORBIDDEN_SERVICE_HEADERS = _bearer_headers({"sub": "rogue-service", "role": "SERVICE", "service": "rogue-service"})


@pytest.fixture
def admin_headers() -> dict[str, str]:
    """Provide admin bearer headers for tests that expect a fixture."""
    return ADMIN_HEADERS


@pytest.fixture
def super_admin_headers() -> dict[str, str]:
    """Provide super-admin bearer headers for tests that expect a fixture."""
    return SUPER_ADMIN_HEADERS


@pytest.fixture
def service_headers() -> dict[str, str]:
    """Provide service bearer headers for tests that expect a fixture."""
    return SERVICE_HEADERS


@pytest.fixture
def forbidden_service_headers() -> dict[str, str]:
    """Provide a disallowed service bearer header for internal auth tests."""
    return FORBIDDEN_SERVICE_HEADERS


@pytest.fixture(scope="session")
def postgres_container() -> str:
    """Start a PostgreSQL 16 container for the entire test session."""
    global _pg_url
    with PostgresContainer("postgres:16-alpine") as pg:
        # Enable btree_gist extension as required by Phase A
        pg.get_container_host_ip()  # Ensure container is ready
        url = pg.get_connection_url()
        _pg_url = url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
        _pg_url = _pg_url.replace("postgresql://", "postgresql+asyncpg://")
        yield _pg_url


@pytest.fixture(scope="session")
def migrated_database(postgres_container: str) -> str:
    """Apply Alembic migrations once to the test database."""
    service_root = Path(__file__).resolve().parents[1]
    alembic_cfg = Config(str(service_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(service_root / "alembic"))
    alembic_cfg.set_main_option("prepend_sys_path", str(service_root / "src"))
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_container)

    # We must ensure btree_gist is enabled before migrations run
    # TestContainers doesn't do this automatically
    # But migration 001 already does 'CREATE EXTENSION IF NOT EXISTS btree_gist'
    command.upgrade(alembic_cfg, "head")
    return postgres_container


@pytest.fixture(scope="session")
def test_db_url(migrated_database: str) -> str:
    """Expose the migrated async database URL to tests that need their own engine."""
    return migrated_database


async def _truncate_all(engine) -> None:
    """Remove all fleet-service rows between tests."""
    table_list = ", ".join(TRUNCATE_TABLES)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE TABLE {table_list} CASCADE"))


@pytest_asyncio.fixture
async def db_engine(migrated_database: str):
    """Create an engine for the current test using the migrated schema."""
    engine = create_async_engine(migrated_database, echo=False, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def reset_database(db_engine) -> AsyncGenerator[None, None]:
    """Ensure every test runs against a clean migrated database."""
    await _truncate_all(db_engine)
    yield
    await _truncate_all(db_engine)


@pytest_asyncio.fixture
async def test_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a session for direct DB manipulation in tests."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_engine, monkeypatch: pytest.MonkeyPatch, respx_mock) -> AsyncGenerator[AsyncClient, None]:
    """Provide a test HTTP client with dependencies stubbed."""

    @asynccontextmanager
    async def noop_lifespan(app: FastAPI):
        yield

    from fleet_service.main import create_app

    test_app = create_app()
    # Override lifespan to avoid prod validation/broker init
    test_app.router.lifespan_context = noop_lifespan

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def override_get_session():
        async with session_factory() as session:
            yield session

    test_app.dependency_overrides[get_session] = override_get_session

    # Patch session factories in other modules if any (e.g. background tasks or health probes)
    monkeypatch.setattr("fleet_service.routers.health.async_session_factory", session_factory)
    monkeypatch.setattr("fleet_service.worker_heartbeats.async_session_factory", session_factory)

    # Mock external clients
    async def mock_validate_driver(driver_id: str):
        return {
            "driver_id": driver_id,
            "exists": True,
            "status": "ACTIVE",
            "lifecycle_state": "ACTIVE",
            "is_assignable": True,
        }

    async def mock_reference_check(asset_id: str, asset_type: str):
        return {
            "asset_id": asset_id,
            "asset_type": asset_type,
            "is_referenced": False,
            "has_references": False,
            "active_trip_count": 0,
        }

    async def stub_get_token(
        *,
        service_name: str,
        audience: str | None,
        token_url: str,
        client_id: str,
        client_secret: str,
    ) -> str:
        del token_url, client_secret
        return sign_test_token(
            TEST_JWKS_BUNDLE,
            sub=service_name,
            role="SERVICE",
            service=client_id,
            aud=audience or settings.auth_audience,
        )

    monkeypatch.setattr("fleet_service.clients.driver_client.validate_driver", mock_validate_driver)
    monkeypatch.setattr("fleet_service.clients.trip_client.check_asset_references", mock_reference_check)
    install_jwks_urlopen_mock(monkeypatch, TEST_JWKS_BUNDLE, jwks_url=settings.auth_jwks_url)
    respx_mock.get(settings.auth_jwks_url).mock(return_value=httpx.Response(200, json=TEST_JWKS_BUNDLE.jwks))
    monkeypatch.setattr("fleet_service.auth._SERVICE_TOKEN_CACHE.get_token", stub_get_token)
    await record_worker_heartbeat("outbox-relay")
    await record_worker_heartbeat("fleet-worker")
    test_app.state.broker = NoOpBroker()

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
