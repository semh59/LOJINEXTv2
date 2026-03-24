"""Shared test fixtures for Trip Service tests.

Uses testcontainers to spin up a real PostgreSQL instance.
Disables background workers in tests.

Connection strategy:
- NullPool ensures connections are not reused across event loops.
- Engine created per-test (cheap with NullPool) to stay on the test's loop.
- Tables created lazily with a sync flag.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer

from trip_service.database import get_session
from trip_service.errors import ProblemDetailError, problem_detail_handler
from trip_service.middleware import RequestIdMiddleware
from trip_service.models import Base
from trip_service.routers import health, import_export, trips

# ---------------------------------------------------------------------------
# PostgreSQL container (session-scoped sync fixture)
# ---------------------------------------------------------------------------

_pg_url: str = ""
_tables_created: bool = False


@pytest.fixture(scope="session", autouse=True)
def postgres_container():
    """Start a PostgreSQL 16 container for the entire test session."""
    global _pg_url
    with PostgresContainer("postgres:16-alpine") as pg:
        url = pg.get_connection_url()
        _pg_url = url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
        _pg_url = _pg_url.replace("postgresql://", "postgresql+asyncpg://")
        yield


# ---------------------------------------------------------------------------
# Engine + session (function-scoped, NullPool avoids cross-loop issues)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_engine(postgres_container):
    """Create an engine for the current test using NullPool.

    NullPool creates fresh connections per operation and never reuses them,
    so there's no cross-loop contamination between tests.
    """
    global _tables_created

    engine = create_async_engine(_pg_url, echo=False, poolclass=NullPool)

    if not _tables_created:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        _tables_created = True

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def test_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a session for direct DB manipulation in tests."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    """Provide a test HTTP client.

    Builds a test FastAPI app with:
    - No lifespan (no background workers)
    - Session dependency using test DB
    """

    @asynccontextmanager
    async def noop_lifespan(app: FastAPI):
        yield

    test_app = FastAPI(lifespan=noop_lifespan)
    test_app.add_middleware(RequestIdMiddleware)
    test_app.add_exception_handler(ProblemDetailError, problem_detail_handler)  # type: ignore[arg-type]
    test_app.include_router(health.router)
    test_app.include_router(trips.router)
    test_app.include_router(import_export.router)

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def override_get_session():
        async with session_factory() as session:
            yield session

    test_app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def make_slip_payload(**overrides: Any) -> dict[str, Any]:
    """Create a valid slip ingest payload."""
    base: dict[str, Any] = {
        "source_type": "TELEGRAM_TRIP_SLIP",
        "source_slip_no": f"SLIP-{datetime.now().timestamp()}",
        "driver_id": "driver-001",
        "vehicle_id": "vehicle-001",
        "origin_name": "Istanbul",
        "destination_name": "Ankara",
        "trip_datetime_local": "2025-06-15T10:30:00",
        "trip_timezone": "Europe/Istanbul",
        "tare_weight_kg": 10000,
        "gross_weight_kg": 25000,
        "net_weight_kg": 15000,
        "ocr_confidence": 0.95,
    }
    base.update(overrides)
    return base


def make_manual_trip_payload(**overrides: Any) -> dict[str, Any]:
    """Create a valid manual trip create payload."""
    base: dict[str, Any] = {
        "trip_no": f"TRIP-{datetime.now().timestamp()}",
        "driver_id": "driver-001",
        "route_id": "route-001",
        "trip_datetime_local": "2025-06-15T10:30:00",
        "trip_timezone": "Europe/Istanbul",
        "tare_weight_kg": 10000,
        "gross_weight_kg": 25000,
        "net_weight_kg": 15000,
    }
    base.update(overrides)
    return base


ADMIN_HEADERS: dict[str, str] = {
    "X-Actor-Type": "ADMIN",
    "X-Actor-Id": "admin-test-001",
}
