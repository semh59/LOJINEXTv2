"""Repo cleanliness assertions for removed trip-service concerns."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TRIP_SERVICE_ROOT = ROOT / "services" / "trip-service"


def test_removed_excel_runtime_files_are_gone() -> None:
    assert not (TRIP_SERVICE_ROOT / "src" / "trip_service" / "routers" / "import_export.py").exists()
    assert not (TRIP_SERVICE_ROOT / "src" / "trip_service" / "workers" / "import_worker.py").exists()
    assert not (TRIP_SERVICE_ROOT / "src" / "trip_service" / "workers" / "export_worker.py").exists()


def test_forbidden_trip_service_terms_are_absent() -> None:
    forbidden_terms = (
        "weather_status",
        "skip_weather_enrichment",
        "openpyxl",
        "python-multipart",
    )
    removed_route_terms = (
        "/api/v1/trips/import-jobs",
        "/api/v1/trips/export-jobs",
    )
    target_paths = [
        TRIP_SERVICE_ROOT / "src",
        TRIP_SERVICE_ROOT / "alembic",
        TRIP_SERVICE_ROOT / ".env.example",
        TRIP_SERVICE_ROOT / "pyproject.toml",
        ROOT / "MEMORY" / "PROJECT_STATE.md",
        ROOT / "TASKS" / "TASK-0001" / "PLAN.md",
        ROOT / "TASKS" / "TASK-0003" / "STATE.md",
    ]

    for target in target_paths:
        if target.is_file():
            files = [target]
        else:
            files = [
                path
                for path in target.rglob("*")
                if path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix in {".py", ".md", ".toml", ".ini", ".example"}
            ]
        for path in files:
            content = path.read_text(encoding="utf-8")
            for term in forbidden_terms:
                assert term not in content, f"Found forbidden term {term!r} in {path}"
            if path.name != "removed_endpoints.py":
                for term in removed_route_terms:
                    assert term not in content, f"Found removed endpoint term {term!r} in {path}"


def test_import_artifacts_are_removed() -> None:
    assert not list((ROOT / "storage" / "imports").rglob("*.xlsx"))
    assert not list((TRIP_SERVICE_ROOT / "storage" / "imports").rglob("*.xlsx"))
