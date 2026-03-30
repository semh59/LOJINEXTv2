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


def test_dockerfile_uses_split_api_runtime_command() -> None:
    dockerfile_path = Path(__file__).resolve().parents[1] / "Dockerfile"
    dockerfile = dockerfile_path.read_text(encoding="utf-8")

    assert 'CMD ["trip-api"]' in dockerfile
