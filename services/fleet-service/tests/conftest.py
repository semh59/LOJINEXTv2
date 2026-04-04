"""Shared test fixtures for Fleet Service tests."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import jwt
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer

from fleet_service.config import settings
from fleet_service.database import get_session
from fleet_service.errors import ProblemDetailError, problem_detail_handler, validation_exception_handler
from fleet_service.middleware import PrometheusMiddleware, RequestIdMiddleware
from fleet_service.broker import NoOpBroker

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


def _token(payload: dict[str, Any]) -> str:
    """Build a JWT token for tests."""
    return jwt.encode(payload, settings.auth_jwt_secret, algorithm=settings.auth_jwt_algorithm)


def _bearer_headers(payload: dict[str, Any]) -> dict[str, str]:
    """Return an Authorization header for the given claims."""
    return {"Authorization": f"Bearer {_token(payload)}"}


ADMIN_HEADERS = _bearer_headers({"sub": "admin-test-001", "role": "ADMIN"})
SUPER_ADMIN_HEADERS = _bearer_headers({"sub": "super-admin-001", "role": "SUPER_ADMIN"})
SERVICE_HEADERS = _bearer_headers({"sub": "fleet-service-test", "role": "SERVICE", "service": "fleet-service-test"})


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
async def client(db_engine, monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[AsyncClient, None]:
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
    async def mock_check_eligibility(*args, **kwargs):
        return {"drivers": {}}  # Default empty

    async def mock_reference_check(*args, **kwargs):
        return {"is_referenced": False, "reference_sources": []}

    monkeypatch.setattr(
        "fleet_service.infrastructure.http_clients.driver_client.DriverClient.check_eligibility", mock_check_eligibility
    )
    monkeypatch.setattr(
        "fleet_service.infrastructure.http_clients.trip_client.TripClient.check_reference", mock_reference_check
    )

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
