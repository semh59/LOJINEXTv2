"""Pytest fixtures and configuration for Driver Service tests."""

from __future__ import annotations

# AGGRESSIVE GLOBAL AUTH PATCH: MUST RUN BEFORE ANY OTHER IMPORTS
import platform_auth.service_tokens
from platform_auth_testing import build_test_jwks_bundle, sign_test_token

_GLOBAL_JWKS_BUNDLE = build_test_jwks_bundle()


async def _global_mock_get_token(*args, **kwargs):
    # Signature: (self, *, service_name, audience, token_url, client_id, client_secret)
    aud = kwargs.get("audience") or (args[2] if len(args) > 2 else "unknown")
    return sign_test_token(
        _GLOBAL_JWKS_BUNDLE,
        sub="test-service",
        role="SERVICE",
        service="test-service",
        aud=aud,
    )


# Overwrite the class method directly at the very beginning
platform_auth.service_tokens.ServiceTokenCache.get_token = _global_mock_get_token

import asyncio  # noqa: E402
from collections.abc import AsyncGenerator  # noqa: E402

import pytest  # noqa: E402
import sqlalchemy  # noqa: E402
from httpx import ASGITransport, AsyncClient, Response  # noqa: E402
import respx  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from testcontainers.postgres import PostgresContainer  # noqa: E402

from driver_service.config import settings  # noqa: E402
from driver_service.database import get_session  # noqa: E402
from driver_service.main import app  # noqa: E402
from driver_service.models import Base  # noqa: E402

TEST_JWKS_BUNDLE = build_test_jwks_bundle()
settings.environment = "test"
settings.auth_jwt_algorithm = "RS256"
settings.auth_issuer = TEST_JWKS_BUNDLE.issuer
settings.auth_audience = TEST_JWKS_BUNDLE.audience
settings.auth_jwks_url = TEST_JWKS_BUNDLE.jwks_url
settings.auth_service_audience = "lojinext-platform"
settings.auth_service_token_url = "http://identity.test/auth/v1/token/service"
settings.auth_service_client_id = settings.service_name
settings.auth_service_client_secret = "driver-client-secret"


def _headers(*, sub: str, role: str, service: str | None = None) -> dict[str, str]:
    token = sign_test_token(TEST_JWKS_BUNDLE, sub=sub, role=role, service=service)
    return {"Authorization": f"Bearer {token}"}


ADMIN_HEADERS = _headers(sub="test-admin-id", role="ADMIN")
MANAGER_HEADERS = _headers(sub="test-manager-id", role="MANAGER")
INTERNAL_HEADERS = _headers(sub="fleet-service", role="SERVICE", service="fleet-service")
FORBIDDEN_INTERNAL_HEADERS = _headers(sub="rogue-service", role="SERVICE", service="rogue-service")


@pytest.fixture(scope="session")
def postgres_container() -> PostgresContainer:
    """Spin up a Postgres 16 container for tests."""
    with PostgresContainer("postgres:16-alpine") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def database_url(postgres_container: PostgresContainer) -> str:
    """Get the SQLAlchemy async URL for the test container."""
    url = postgres_container.get_connection_url()
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
        await conn.execute(sqlalchemy.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.create_all)

    test_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    import driver_service.database
    import driver_service.routers
    import driver_service.routers.import_jobs

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


@pytest.fixture(scope="function")
async def client(db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[AsyncClient, None]:
    """Provide httpx AsyncClient backed by real RS256 auth and test DB session."""

    def override_get_session() -> AsyncSession:
        return db_session

    app.dependency_overrides[get_session] = override_get_session
    # Mock JWKS for both sync and async httpx calls
    with respx.mock(assert_all_called=False) as respx_mock:
        respx_mock.get(settings.auth_jwks_url).mock(return_value=Response(200, json=TEST_JWKS_BUNDLE.jwks))

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


@pytest.fixture
def auth_admin() -> dict[str, str]:
    return ADMIN_HEADERS


@pytest.fixture
def auth_manager() -> dict[str, str]:
    return MANAGER_HEADERS


@pytest.fixture
def auth_internal() -> dict[str, str]:
    return INTERNAL_HEADERS


@pytest.fixture
def forbidden_internal() -> dict[str, str]:
    return FORBIDDEN_INTERNAL_HEADERS
