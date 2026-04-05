from __future__ import annotations

import json
import os
import asyncio
from pathlib import Path

import httpx
import pytest

DB_PATH = Path(__file__).resolve().parent / "identity_test.db"

if os.getenv("IDENTITY_TEST_BACKEND", "").strip().lower() != "postgres":
    os.environ["IDENTITY_DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"
os.environ["IDENTITY_ENVIRONMENT"] = "test"
os.environ["IDENTITY_BOOTSTRAP_SUPERADMIN_USERNAME"] = "bootstrap-admin"
os.environ["IDENTITY_BOOTSTRAP_SUPERADMIN_EMAIL"] = "bootstrap@example.com"
os.environ["IDENTITY_BOOTSTRAP_SUPERADMIN_PASSWORD"] = "bootstrap-password"
os.environ["IDENTITY_SERVICE_CLIENTS"] = "trip-service"
os.environ["IDENTITY_SERVICE_CLIENT_SECRET__TRIP_SERVICE"] = "trip-client-secret"
os.environ["IDENTITY_BOOTSTRAP_SERVICE_CLIENTS_JSON"] = ""
os.environ["IDENTITY_KEY_ENCRYPTION_KEY_B64"] = os.getenv(
    "IDENTITY_KEY_ENCRYPTION_KEY_B64",
    "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
)
os.environ["IDENTITY_KEY_ENCRYPTION_KEY_VERSION"] = os.getenv("IDENTITY_KEY_ENCRYPTION_KEY_VERSION", "test-v1")

from identity_service.database import async_session_factory, engine  # noqa: E402
from identity_service.main import app  # noqa: E402
from identity_service.models import Base  # noqa: E402
from identity_service.token_service import seed_bootstrap_state  # noqa: E402


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
async def reset_db() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    async with async_session_factory() as session:
        await seed_bootstrap_state(session)
        await session.commit()
    yield
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client
