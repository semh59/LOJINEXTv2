"""Pytest fixtures and configuration for Driver Service tests.

Provides TestContainers-backed PostgreSQL database and FastAPI TestClient.
"""

import asyncio
from typing import AsyncGenerator

import pytest
import sqlalchemy
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from driver_service.auth import (
    AuthContext,
    admin_auth_dependency,
    admin_or_internal_auth_dependency,
    admin_or_manager_auth_dependency,
    internal_service_auth_dependency,
)
from driver_service.database import get_session
from driver_service.main import app
from driver_service.models import Base

# ---------------------------------------------------------------------------
# TestContainers Setup
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def postgres_container() -> PostgresContainer:
    """Spin up a Postgres 16 container for tests."""
    with PostgresContainer("postgres:16-alpine") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def database_url(postgres_container: PostgresContainer) -> str:
    """Get the SQLAlchemy async URL for the test container."""
    url = postgres_container.get_connection_url()
    # Replace psycopg2 mapping with asyncpg
    return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def engine(database_url: str):
    """Create global async engine for the test session."""
    engine = create_async_engine(database_url, echo=False)

    async with engine.begin() as conn:
        # Enable pg_trgm for fuzzy search tests
        await conn.execute(sqlalchemy.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        # Create all tables directly (skipping alembic for unit/integration speed)
        await conn.run_sync(Base.metadata.create_all)

    # Patch global factories for background tasks
    from sqlalchemy.ext.asyncio import async_sessionmaker

    import driver_service.database
    import driver_service.routers
    import driver_service.routers.import_jobs

    test_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    driver_service.database.async_session_factory = test_factory
    driver_service.routers.async_session_factory = test_factory
    driver_service.routers.import_jobs.async_session_factory = test_factory

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(scope="function")
async def db_session(engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a clean database session for each test via nesting/rollback."""
    connection = await engine.connect()
    transaction = await connection.begin()
    session_maker = async_sessionmaker(bind=connection, expire_on_commit=False)
    session = session_maker()

    yield session

    await session.close()
    await transaction.rollback()
    await connection.close()


# ---------------------------------------------------------------------------
# FastAPI Test Client and Auth Mocks
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provide httpx AsyncClient tailored for the FastAPI app with auth mocks."""

    def override_get_session() -> AsyncSession:
        return db_session

    def override_admin_auth() -> AuthContext:
        return AuthContext(actor_id="test-admin-id", role="ADMIN")

    def override_manager_auth() -> AuthContext:
        return AuthContext(actor_id="test-manager-id", role="MANAGER")

    def override_internal_auth() -> AuthContext:
        return AuthContext(actor_id="test-internal-id", role="INTERNAL_SERVICE")

    app.dependency_overrides[get_session] = override_get_session

    # We map specific headers to roles as a simple way to test role auth in integration tests.
    # But since Depends resolves before the endpoint body, we can just override the dependencies
    # to look at the request headers and return appropriate mock context.

    from fastapi import Request

    async def mock_auth_dep(request: Request):
        auth_header = request.headers.get("Authorization", "")
        if "admin" in auth_header.lower():
            return AuthContext(actor_id="test-admin-id", role="ADMIN")
        elif "manager" in auth_header.lower():
            return AuthContext(actor_id="test-manager-id", role="MANAGER")
        elif "internal" in auth_header.lower():
            return AuthContext(actor_id="test-internal-id", role="INTERNAL_SERVICE")
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Unauthorized")

    app.dependency_overrides[admin_auth_dependency] = mock_auth_dep
    app.dependency_overrides[admin_or_manager_auth_dependency] = mock_auth_dep
    app.dependency_overrides[internal_service_auth_dependency] = mock_auth_dep
    app.dependency_overrides[admin_or_internal_auth_dependency] = mock_auth_dep

    class HealthyBroker:
        async def check_health(self) -> bool:
            return True

        async def close(self) -> None:
            return None

    had_broker = hasattr(app.state, "broker")
    original_broker = getattr(app.state, "broker", None)
    app.state.broker = HealthyBroker()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    if had_broker:
        app.state.broker = original_broker
    elif hasattr(app.state, "broker"):
        delattr(app.state, "broker")


# Authentication Headers
@pytest.fixture
def auth_admin() -> dict[str, str]:
    return {"Authorization": "Bearer admin-token-mock"}


@pytest.fixture
def auth_manager() -> dict[str, str]:
    return {"Authorization": "Bearer manager-token-mock"}


@pytest.fixture
def auth_internal() -> dict[str, str]:
    return {"Authorization": "Bearer internal-token-mock"}
