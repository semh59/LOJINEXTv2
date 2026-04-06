"""Runtime split regression tests for Trip Service."""

from __future__ import annotations

import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from trip_service.main import create_app


class _FakeBroker:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True

    async def check_health(self) -> None:
        return None


@pytest.mark.asyncio
async def test_api_lifespan_initializes_broker_without_worker_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    broker = _FakeBroker()
    shutdown_markers = {"http_clients_closed": False, "engine_disposed": False}

    async def fake_close_http_clients() -> None:
        shutdown_markers["http_clients_closed"] = True

    async def fake_dispose() -> None:
        shutdown_markers["engine_disposed"] = True

    monkeypatch.setattr("trip_service.main.create_broker", lambda broker_type: broker)
    monkeypatch.setattr("trip_service.main.close_http_clients", fake_close_http_clients)
    monkeypatch.setattr("trip_service.main.engine", SimpleNamespace(dispose=fake_dispose))

    app = create_app()

    async with app.router.lifespan_context(app):
        assert app.state.broker is broker
        assert not hasattr(app.state, "worker_tasks")

    assert broker.closed is True
    assert shutdown_markers == {"http_clients_closed": True, "engine_disposed": True}


def test_project_scripts_expose_split_runtime_commands() -> None:
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"] == {
        "trip-api": "trip_service.entrypoints.api:main",
        "trip-enrichment-worker": "trip_service.entrypoints.enrichment_worker:main",
        "trip-outbox-worker": "trip_service.entrypoints.outbox_worker:main",
        "trip-cleanup-worker": "trip_service.entrypoints.cleanup_worker:main",
    }


def test_project_wires_shared_platform_packages() -> None:
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    assert "platform-auth" in pyproject["project"]["dependencies"]
    assert "platform-common" in pyproject["project"]["dependencies"]
    assert pyproject["tool"]["pytest"]["ini_options"]["pythonpath"] == [
        "src",
        "../../packages/platform-auth/src",
        "../../packages/platform-auth/tests/support",
        "../../packages/platform-common/src",
    ]
    assert pyproject["tool"]["uv"]["sources"] == {
        "platform-auth": {"path": "../../packages/platform-auth"},
        "platform-common": {"path": "../../packages/platform-common"},
    }


def test_app_registers_exact_trip_and_health_routes() -> None:
    app = create_app()
    route_paths = {route.path for route in app.routes}
    route_methods: dict[str, set[str]] = {}
    for route in app.routes:
        route_methods.setdefault(route.path, set()).update(route.methods or set())

    expected_paths = {
        "/api/v1/trips",
        "/api/v1/trips/{trip_id}",
        "/api/v1/trips/{trip_id}/timeline",
        "/api/v1/trips/{trip_id}/approve",
        "/api/v1/trips/{trip_id}/reject",
        "/api/v1/trips/{trip_id}/cancel",
        "/api/v1/trips/{trip_id}/hard-delete",
        "/api/v1/trips/{base_trip_id}/empty-return",
        "/api/v1/trips/{trip_id}/retry-enrichment",
        "/internal/v1/trips/driver-check/{driver_id}",
        "/internal/v1/assets/reference-check",
        "/internal/v1/trips/slips/ingest",
        "/internal/v1/trips/slips/ingest-fallback",
        "/internal/v1/trips/excel/ingest",
        "/internal/v1/trips/excel/export-feed",
        "/health",
        "/ready",
        "/metrics",
    }
    unexpected_paths = {
        "/api/v1/api/v1/trips",
        "/api/v1/internal/v1/assets/reference-check",
        "/v1/health",
        "/v1/ready",
        "/v1/metrics",
    }

    assert expected_paths.issubset(route_paths)
    assert not unexpected_paths & route_paths
    assert route_methods["/api/v1/trips"] == {"GET", "POST"}
    assert route_methods["/api/v1/trips/{trip_id}"] == {"GET", "PATCH"}
    assert route_methods["/api/v1/trips/{trip_id}/timeline"] == {"GET"}
    assert route_methods["/api/v1/trips/{trip_id}/approve"] == {"POST"}
    assert route_methods["/api/v1/trips/{trip_id}/reject"] == {"POST"}
    assert route_methods["/api/v1/trips/{trip_id}/cancel"] == {"POST"}
    assert route_methods["/api/v1/trips/{trip_id}/hard-delete"] == {"POST"}
    assert route_methods["/health"] == {"GET"}
    assert route_methods["/ready"] == {"GET"}
    assert route_methods["/metrics"] == {"GET"}


def test_dockerfile_uses_split_api_runtime_command() -> None:
    dockerfile_path = Path(__file__).resolve().parents[1] / "Dockerfile"
    dockerfile = dockerfile_path.read_text(encoding="utf-8")

    assert 'CMD ["trip-api"]' in dockerfile
    assert "packages/platform-auth" in dockerfile
    assert "packages/platform-common" in dockerfile
