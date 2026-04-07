"""Shared test fixtures for Trip Service tests."""

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

from collections.abc import AsyncGenerator  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from datetime import UTC, datetime, timedelta  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from platform_auth_testing import install_jwks_urlopen_mock  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402
from testcontainers.postgres import PostgresContainer  # noqa: E402

from alembic import command  # noqa: E402
from trip_service.broker import NoOpBroker  # noqa: E402
from trip_service.config import settings  # noqa: E402
from trip_service.database import get_session  # noqa: E402
from trip_service.dependencies import LocationRouteResolution, LocationTripContext  # noqa: E402
from trip_service.errors import ProblemDetailError, problem_detail_handler, validation_exception_handler  # noqa: E402
from trip_service.middleware import PrometheusMiddleware, RequestIdMiddleware  # noqa: E402
from trip_service.routers import driver_statement, health, removed_endpoints, trips  # noqa: E402
from trip_service.worker_heartbeats import record_worker_heartbeat  # noqa: E402

TRUNCATE_TABLES = (
    "trip_trip_timeline",
    "trip_trip_evidence",
    "trip_trip_enrichment",
    "trip_trip_delete_audit",
    "trip_outbox",
    "trip_idempotency_records",
    "trip_trips",
    "worker_heartbeats",
)

_pg_url: str = ""
_TEST_TZ = ZoneInfo("Europe/Istanbul")
TEST_JWKS_BUNDLE = build_test_jwks_bundle()
settings.environment = "test"
settings.auth_jwt_algorithm = "RS256"
settings.auth_issuer = TEST_JWKS_BUNDLE.issuer
settings.auth_audience = TEST_JWKS_BUNDLE.audience
settings.auth_jwks_url = TEST_JWKS_BUNDLE.jwks_url
settings.auth_service_token_url = "http://identity.test/auth/v1/token/service"
settings.auth_service_client_id = settings.service_name
settings.auth_service_client_secret = "trip-client-secret"


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
    return sign_test_token(
        TEST_JWKS_BUNDLE,
        sub=str(payload["sub"]),
        role=str(payload["role"]),
        service=str(payload["service"]) if payload.get("service") is not None else None,
        extra_claims={key: value for key, value in payload.items() if key not in {"sub", "role", "service"}},
    )


def _bearer_headers(payload: dict[str, Any]) -> dict[str, str]:
    """Return an Authorization header for the given claims."""
    return {"Authorization": f"Bearer {_token(payload)}"}


ADMIN_HEADERS: dict[str, str] = _bearer_headers({"sub": "admin-test-001", "role": "MANAGER"})
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
async def client(db_engine, monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[AsyncClient, None]:
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

    async def allow_all_trip_references(**kwargs: Any) -> None:
        return None

    async def healthy_dependency_probe() -> bool:
        return True

    test_app = FastAPI(lifespan=noop_lifespan)
    test_app.add_middleware(PrometheusMiddleware)
    test_app.add_middleware(RequestIdMiddleware)
    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "If-Match", "Idempotency-Key", "X-Idempotency-Key"],
        expose_headers=["ETag", "X-Correlation-ID"],
    )
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

    test_app.dependency_overrides[get_session] = override_get_session
    install_jwks_urlopen_mock(monkeypatch, TEST_JWKS_BUNDLE, jwks_url=settings.auth_jwks_url)

    # Also patch the global database factory to ensure heartbeats use the test engine
    import trip_service.database

    monkeypatch.setattr(trip_service.database, "async_session_factory", session_factory)
    monkeypatch.setattr("trip_service.routers.health.async_session_factory", session_factory)
    monkeypatch.setattr("trip_service.worker_heartbeats.async_session_factory", session_factory)
    monkeypatch.setattr("trip_service.routers.health.probe_fleet_service", healthy_dependency_probe)
    monkeypatch.setattr("trip_service.routers.health.probe_location_service", healthy_dependency_probe)
    monkeypatch.setattr("trip_service.routers.trips.ensure_trip_references_valid", allow_all_trip_references)
    monkeypatch.setattr("trip_service.routers.trips.fetch_trip_context", stub_fetch_trip_context)
    monkeypatch.setattr("trip_service.routers.trips.resolve_route_by_names", stub_resolve_route_by_names)

    # Initialize heartbeats for health checks
    await record_worker_heartbeat("enrichment-worker")
    await record_worker_heartbeat("outbox-relay")
    await record_worker_heartbeat("cleanup-worker")

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
