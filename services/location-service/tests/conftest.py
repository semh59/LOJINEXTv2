"""Shared test fixtures for Location Service tests.

Uses testcontainers to spin up a real PostgreSQL instance.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer

from location_service.config import settings
from location_service.errors import ProblemDetailError, problem_detail_handler
from location_service.middleware import RequestIdMiddleware
from location_service.models import Base
from location_service.routers import health, internal_routes, pairs, points, processing

# ---------------------------------------------------------------------------
# PostgreSQL container (session-scoped sync fixture)
# ---------------------------------------------------------------------------

_pg_url: str = ""
_tables_created: bool = False


@pytest.fixture(scope="session")
def postgres_container():
    """Start a PostgreSQL 16 container for the entire test session."""
    global _pg_url
    with PostgresContainer("postgres:16-alpine") as pg:
        url = pg.get_connection_url()
        _pg_url = url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
        _pg_url = _pg_url.replace("postgresql://", "postgresql+asyncpg://")

        # Override settings for tests
        settings.database_url = _pg_url
        yield


# ---------------------------------------------------------------------------
# Engine + session (function-scoped, NullPool avoids cross-loop issues)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_engine(postgres_container):
    """Create an engine for the current test using NullPool."""
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
    """Provide a test HTTP client."""

    @asynccontextmanager
    async def noop_lifespan(app: FastAPI):
        yield

    test_app = FastAPI(lifespan=noop_lifespan)
    test_app.add_middleware(RequestIdMiddleware)
    test_app.add_exception_handler(ProblemDetailError, problem_detail_handler)  # type: ignore[arg-type]
    test_app.include_router(health.router)
    test_app.include_router(points.router)
    test_app.include_router(pairs.router)
    test_app.include_router(processing.router)
    test_app.include_router(internal_routes.router)

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    # Patch the global session factory so direct users get test DB
    import location_service.database
    import location_service.processing.pipeline
    import location_service.routers.health

    original_factory = location_service.database.async_session_factory
    location_service.database.async_session_factory = session_factory
    location_service.routers.health.async_session_factory = session_factory
    location_service.processing.pipeline.async_session_factory = session_factory

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Restore original
    location_service.database.async_session_factory = original_factory
    location_service.routers.health.async_session_factory = original_factory
    location_service.processing.pipeline.async_session_factory = original_factory
