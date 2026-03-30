"""Runtime split regression tests for Location Service."""

from __future__ import annotations

import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from location_service.main import create_app


@pytest.mark.asyncio
async def test_api_lifespan_validates_without_starting_processing_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    markers = {"logging": False, "validated": False, "disposed": False}

    def fake_setup_logging() -> None:
        markers["logging"] = True

    def fake_validate_prod_settings(_settings) -> None:
        markers["validated"] = True

    async def fake_dispose() -> None:
        markers["disposed"] = True

    monkeypatch.setattr("location_service.main.setup_logging", fake_setup_logging)
    monkeypatch.setattr("location_service.main.validate_prod_settings", fake_validate_prod_settings)
    monkeypatch.setattr("location_service.main.engine", SimpleNamespace(dispose=fake_dispose))

    app = create_app()

    async with app.router.lifespan_context(app):
        assert getattr(app.state, "processing_worker", None) is None

    assert markers == {"logging": True, "validated": True, "disposed": True}


def test_project_scripts_expose_split_runtime_commands() -> None:
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"] == {
        "location-api": "location_service.entrypoints.api:main",
        "location-processing-worker": "location_service.entrypoints.processing_worker:main",
    }


def test_dockerfile_uses_split_api_runtime_command() -> None:
    dockerfile_path = Path(__file__).resolve().parents[1] / "Dockerfile"
    dockerfile = dockerfile_path.read_text(encoding="utf-8")

    assert 'CMD ["location-api"]' in dockerfile
