"""Shared test fixtures for Trip Service tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import jwt
import pytest
import pytest_asyncio
from alembic.config import Config
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer

from alembic import command
from trip_service.broker import NoOpBroker
from trip_service.config import settings
from trip_service.database import get_session
from trip_service.dependencies import LocationRouteResolution, LocationTripContext
from trip_service.errors import ProblemDetailError, problem_detail_handler, validation_exception_handler
from trip_service.middleware import PrometheusMiddleware, RequestIdMiddleware
from trip_service.routers import driver_statement, health, removed_endpoints, trips
from trip_service.worker_heartbeats import record_worker_heartbeat

TRUNCATE_TABLES = (
    "trip_trip_timeline",
    "trip_trip_evidence",
    "trip_trip_enrichment",
    "trip_trip_delete_audit",
    "trip_outbox",
    "trip_idempotency_records",
    "trip_trips",
)

_pg_url: str = ""
_TEST_TZ = ZoneInfo("Europe/Istanbul")


@dataclass(frozen=True)
class StubPair:
    pair_id: str
    origin_location_id: str
    origin_name: str
    destination_location_id: str
    destination_name: str
    forward_route_id: str
    forward_duration_s: int
    reverse_route_id: str
    reverse_duration_s: int


PAIR_CONTEXTS: dict[str, StubPair] = {
    "pair-001": StubPair(
        pair_id="pair-001",
        origin_location_id="loc-istanbul",
        origin_name="Istanbul",
        destination_location_id="loc-ankara",
        destination_name="Ankara",
        forward_route_id="route-ist-ank",
        forward_duration_s=6 * 3600,
        reverse_route_id="route-ank-ist",
        reverse_duration_s=6 * 3600,
    ),
    "pair-002": StubPair(
        pair_id="pair-002",
        origin_location_id="loc-izmir",
        origin_name="Izmir",
        destination_location_id="loc-bursa",
        destination_name="Bursa",
        forward_route_id="route-izm-bur",
        forward_duration_s=4 * 3600,
        reverse_route_id="route-bur-izm",
        reverse_duration_s=4 * 3600,
    ),
}

NAME_TO_PAIR: dict[tuple[str, str], str] = {
    ("Istanbul", "Ankara"): "pair-001",
    ("Izmir", "Bursa"): "pair-002",
}


def _token(payload: dict[str, Any]) -> str:
    """Build a JWT token for tests."""
    return jwt.encode(payload, settings.auth_jwt_secret, algorithm=settings.auth_jwt_algorithm)


def _bearer_headers(payload: dict[str, Any]) -> dict[str, str]:
    """Return an Authorization header for the given claims."""
    return {"Authorization": f"Bearer {_token(payload)}"}


ADMIN_HEADERS: dict[str, str] = _bearer_headers({"sub": "admin-test-001", "role": "ADMIN"})
SUPER_ADMIN_HEADERS: dict[str, str] = _bearer_headers({"sub": "super-admin-001", "role": "SUPER_ADMIN"})
TELEGRAM_SERVICE_HEADERS: dict[str, str] = _bearer_headers(
    {"sub": "telegram-service", "role": "SERVICE", "service": "telegram-service"}
)
EXCEL_SERVICE_HEADERS: dict[str, str] = _bearer_headers(
    {"sub": "excel-service", "role": "SERVICE", "service": "excel-service"}
)


def _now_local() -> datetime:
    """Return the current time in Europe/Istanbul for payload generation."""
    return datetime.now(_TEST_TZ).replace(microsecond=0)


def _iso_local(dt: datetime) -> str:
    """Serialize a timezone-aware Istanbul datetime without offset information."""
    return dt.astimezone(_TEST_TZ).replace(tzinfo=None).isoformat(timespec="minutes")


@pytest.fixture(scope="session")
def postgres_container() -> str:
    """Start a PostgreSQL 16 container for the entire test session."""
    global _pg_url
    with PostgresContainer("postgres:16-alpine") as pg:
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
    command.upgrade(alembic_cfg, "head")
    return postgres_container


async def _truncate_all(engine) -> None:  # noqa: ANN001
    """Remove all trip-service rows between tests."""
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
async def reset_database(db_engine) -> AsyncGenerator[None, None]:  # noqa: ANN001
    """Ensure every test runs against a clean migrated database."""
    await _truncate_all(db_engine)
    yield
    await _truncate_all(db_engine)


@pytest_asyncio.fixture
async def test_session(db_engine) -> AsyncGenerator[AsyncSession, None]:  # noqa: ANN001
    """Provide a session for direct DB manipulation in tests."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_engine, monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[AsyncClient, None]:  # noqa: ANN001
    """Provide a test HTTP client with dependency probes and route context stubbed healthy."""

    @asynccontextmanager
    async def noop_lifespan(app: FastAPI):
        yield

    async def stub_fetch_trip_context(pair_id: str, field_name: str = "body.route_pair_id") -> LocationTripContext:
        del field_name
        pair = PAIR_CONTEXTS.get(pair_id)
        if pair is None:
            raise AssertionError(f"Unknown test pair_id: {pair_id}")
        return LocationTripContext(
            pair_id=pair.pair_id,
            origin_location_id=pair.origin_location_id,
            origin_name=pair.origin_name,
            destination_location_id=pair.destination_location_id,
            destination_name=pair.destination_name,
            forward_route_id=pair.forward_route_id,
            forward_duration_s=pair.forward_duration_s,
            reverse_route_id=pair.reverse_route_id,
            reverse_duration_s=pair.reverse_duration_s,
            profile_code="TIR",
            pair_status="ACTIVE",
        )

    async def stub_resolve_route_by_names(
        *,
        origin_name: str,
        destination_name: str,
        profile_code: str = "TIR",
        language_hint: str = "AUTO",
    ) -> LocationRouteResolution:
        del profile_code, language_hint
        pair_id = NAME_TO_PAIR.get((origin_name, destination_name))
        if pair_id is None:
            raise AssertionError(f"Unknown resolve pair for {(origin_name, destination_name)}")
        pair = PAIR_CONTEXTS[pair_id]
        return LocationRouteResolution(route_id=pair.forward_route_id, pair_id=pair_id, resolution="EXACT_TR")

    async def dependency_ok() -> bool:
        return True

    async def allow_all_trip_references(**kwargs: Any) -> None:
        return None

    test_app = FastAPI(lifespan=noop_lifespan)
    test_app.add_middleware(RequestIdMiddleware)
    test_app.add_middleware(PrometheusMiddleware)
    test_app.add_exception_handler(ProblemDetailError, problem_detail_handler)  # type: ignore[arg-type]
    test_app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    test_app.include_router(health.router)
    test_app.include_router(removed_endpoints.router)
    test_app.include_router(trips.router)
    test_app.include_router(driver_statement.router)
    test_app.state.broker = NoOpBroker()

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def override_get_session():
        async with session_factory() as session:
            yield session

    record_worker_heartbeat("enrichment-worker")
    record_worker_heartbeat("outbox-relay")
    record_worker_heartbeat("cleanup-worker")

    test_app.dependency_overrides[get_session] = override_get_session
    monkeypatch.setattr("trip_service.routers.health.async_session_factory", session_factory)
    monkeypatch.setattr("trip_service.routers.health.probe_location_service", dependency_ok)
    monkeypatch.setattr("trip_service.routers.health.probe_fleet_service", dependency_ok)
    monkeypatch.setattr("trip_service.routers.trips.ensure_trip_references_valid", allow_all_trip_references)
    monkeypatch.setattr("trip_service.routers.trips.fetch_trip_context", stub_fetch_trip_context)
    monkeypatch.setattr("trip_service.routers.trips.resolve_route_by_names", stub_resolve_route_by_names)

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def make_manual_trip_payload(**overrides: Any) -> dict[str, Any]:
    """Create a valid manual trip create payload."""
    base: dict[str, Any] = {
        "trip_no": f"TRIP-{datetime.now().timestamp()}",
        "route_pair_id": "pair-001",
        "trip_start_local": _iso_local(_now_local() - timedelta(minutes=5)),
        "trip_timezone": "Europe/Istanbul",
        "driver_id": "driver-001",
        "vehicle_id": "vehicle-001",
        "tare_weight_kg": 10000,
        "gross_weight_kg": 25000,
        "net_weight_kg": 15000,
    }
    base.update(overrides)
    return base


def make_slip_payload(**overrides: Any) -> dict[str, Any]:
    """Create a valid Telegram slip ingest payload."""
    stamp = str(datetime.now().timestamp()).replace(".", "")
    base: dict[str, Any] = {
        "source_type": "TELEGRAM_TRIP_SLIP",
        "source_slip_no": f"SLIP-{stamp}",
        "source_reference_key": f"telegram-message-{stamp}",
        "driver_id": "driver-001",
        "vehicle_id": "vehicle-001",
        "origin_name": "Istanbul",
        "destination_name": "Ankara",
        "trip_start_local": _iso_local(_now_local() - timedelta(minutes=10)),
        "trip_timezone": "Europe/Istanbul",
        "tare_weight_kg": 10000,
        "gross_weight_kg": 25000,
        "net_weight_kg": 15000,
        "ocr_confidence": 0.95,
    }
    base.update(overrides)
    return base


def make_fallback_payload(**overrides: Any) -> dict[str, Any]:
    """Create a valid Telegram fallback ingest payload."""
    stamp = str(datetime.now().timestamp()).replace(".", "")
    base: dict[str, Any] = {
        "source_reference_key": f"telegram-message-{stamp}",
        "driver_id": "driver-001",
        "message_sent_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "fallback_reason": "PARSE_FAILED",
    }
    base.update(overrides)
    return base


def make_excel_payload(**overrides: Any) -> dict[str, Any]:
    """Create a valid Excel ingest payload."""
    stamp = str(datetime.now().timestamp()).replace(".", "")
    base: dict[str, Any] = {
        "source_type": "EXCEL_IMPORT",
        "source_reference_key": f"excel-row-{stamp}",
        "trip_no": f"EXCEL-{stamp}",
        "route_pair_id": "pair-002",
        "trip_start_local": _iso_local(_now_local() - timedelta(minutes=15)),
        "trip_timezone": "Europe/Istanbul",
        "driver_id": "driver-001",
        "vehicle_id": "vehicle-001",
        "tare_weight_kg": 12000,
        "gross_weight_kg": 28000,
        "net_weight_kg": 16000,
        "row_number": 1,
    }
    base.update(overrides)
    return base
