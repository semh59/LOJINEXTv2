from __future__ import annotations

from collections.abc import AsyncGenerator

import os
import asyncio

import httpx
import pytest
from sqlalchemy import text
from testcontainers.postgres import PostgresContainer

os.environ["AUTH_ENVIRONMENT"] = "test"
os.environ["AUTH_BOOTSTRAP_SUPERADMIN_USERNAME"] = "bootstrap-admin"
os.environ["AUTH_BOOTSTRAP_SUPERADMIN_EMAIL"] = "bootstrap@example.com"
os.environ["AUTH_BOOTSTRAP_SUPERADMIN_PASSWORD"] = "bootstrap-password"
os.environ["AUTH_SERVICE_CLIENTS"] = "trip-service"
os.environ["AUTH_SERVICE_CLIENT_SECRET__TRIP_SERVICE"] = "trip-client-secret"
os.environ["AUTH_BOOTSTRAP_SERVICE_CLIENTS_JSON"] = ""
os.environ["AUTH_KEY_ENCRYPTION_KEY_B64"] = os.getenv(
    "AUTH_KEY_ENCRYPTION_KEY_B64",
    "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
)
os.environ["AUTH_KEY_ENCRYPTION_KEY_VERSION"] = os.getenv(
    "AUTH_KEY_ENCRYPTION_KEY_VERSION", "test-v1"
)
# Use a fake Redis in tests ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â no real Redis required
os.environ["AUTH_REDIS_URL"] = "redis://localhost:6379/0"  # overridden below

# ---- Start PostgresContainer early if no URL is provided ----
_pg_container = None
if not os.getenv("AUTH_DATABASE_URL"):
    _pg_container = PostgresContainer("postgres:16-alpine")
    _pg_container.start()
    _pg_url = (
        _pg_container.get_connection_url()
        .replace("postgresql+psycopg2://", "postgresql+asyncpg://")
        .replace("postgresql://", "postgresql+asyncpg://")
    )
    os.environ["AUTH_DATABASE_URL"] = _pg_url

# Now import the service modules
import fakeredis.aioredis as fakeredis_aio  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402
from auth_service.database import engine, async_session_factory  # noqa: E402
from auth_service.main import app  # noqa: E402
from auth_service.models import Base  # noqa: E402
from auth_service.redis_client import override_redis  # noqa: E402
from auth_service.token_service import seed_bootstrap_state  # noqa: E402

# Inject fake Redis so tests don't need a real Redis server
_fake_redis = fakeredis_aio.FakeRedis(decode_responses=True)
override_redis(_fake_redis)


def pytest_sessionfinish(session, exitstatus):
    if _pg_container:
        _pg_container.stop()


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
async def reset_db() -> None:
    # Reset db per test
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        await seed_bootstrap_state(session)
        await session.commit()

    # Flush fake Redis so rate limit state doesn't bleed between tests
    await _fake_redis.flushall()

    yield
    # No need to drop fully if we recreate next test, but good practice
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))


@pytest.fixture
async def client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as async_client:
        yield async_client


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
