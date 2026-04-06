"""Deep tests for split runtime entrypoints."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import trip_service.entrypoints._runtime as runtime_entrypoint
import trip_service.entrypoints.api as api_entrypoint
import trip_service.entrypoints.cleanup_worker as cleanup_entrypoint
import trip_service.entrypoints.enrichment_worker as enrichment_entrypoint
import trip_service.entrypoints.outbox_worker as outbox_entrypoint

pytestmark = pytest.mark.runtime


def test_configure_process_calls_logging_and_prod_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(runtime_entrypoint, "setup_logging", lambda: calls.append("logging"))
    monkeypatch.setattr(
        runtime_entrypoint,
        "validate_prod_settings",
        lambda current: calls.append(current.service_name),
    )

    runtime_entrypoint.configure_process()

    assert calls == ["logging", runtime_entrypoint.settings.service_name]


@pytest.mark.asyncio
async def test_shutdown_process_closes_http_clients_and_disposes_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake_close_http_clients() -> None:
        calls.append("http")

    async def fake_dispose() -> None:
        calls.append("engine")

    monkeypatch.setattr(runtime_entrypoint, "close_http_clients", fake_close_http_clients)
    monkeypatch.setattr(runtime_entrypoint, "engine", SimpleNamespace(dispose=fake_dispose))

    await runtime_entrypoint.shutdown_process()

    assert calls == ["http", "engine"]


def test_api_main_calls_uvicorn_with_environment_sensitive_reload(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(api_entrypoint.settings, "service_port", 8101)
    monkeypatch.setattr(api_entrypoint.settings, "environment", "dev")
    monkeypatch.setattr(
        api_entrypoint.uvicorn,
        "run",
        lambda *args, **kwargs: captured.update({"args": args, "kwargs": kwargs}),
    )

    api_entrypoint.main()

    assert captured["args"] == ("trip_service.entrypoints.api:app",)
    assert captured["kwargs"] == {"host": "0.0.0.0", "port": 8101, "reload": True}


@pytest.mark.asyncio
async def test_cleanup_worker_run_configures_and_shuts_down(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake_run_cleanup_loop() -> None:
        calls.append("loop")

    async def fake_shutdown() -> None:
        calls.append("shutdown")

    monkeypatch.setattr(cleanup_entrypoint, "configure_process", lambda: calls.append("configure"))
    monkeypatch.setattr(cleanup_entrypoint, "run_cleanup_loop", fake_run_cleanup_loop)
    monkeypatch.setattr(cleanup_entrypoint, "shutdown_process", fake_shutdown)

    await cleanup_entrypoint._run()

    assert calls == ["configure", "loop", "shutdown"]


@pytest.mark.asyncio
async def test_enrichment_worker_run_configures_and_shuts_down(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake_run_worker() -> None:
        calls.append("worker")

    async def fake_shutdown() -> None:
        calls.append("shutdown")

    monkeypatch.setattr(enrichment_entrypoint, "configure_process", lambda: calls.append("configure"))
    monkeypatch.setattr(enrichment_entrypoint, "run_enrichment_worker", fake_run_worker)
    monkeypatch.setattr(enrichment_entrypoint, "shutdown_process", fake_shutdown)

    await enrichment_entrypoint._run()

    assert calls == ["configure", "worker", "shutdown"]


@pytest.mark.asyncio
async def test_outbox_worker_run_creates_broker_and_shuts_down(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    broker = object()

    async def fake_run_outbox_relay(received_broker) -> None:
        calls.append(type(received_broker).__name__)

    async def fake_shutdown() -> None:
        calls.append("shutdown")

    monkeypatch.setattr(outbox_entrypoint, "configure_process", lambda: calls.append("configure"))
    monkeypatch.setattr(outbox_entrypoint, "create_broker", lambda broker_type: broker)
    monkeypatch.setattr(outbox_entrypoint, "run_outbox_relay", fake_run_outbox_relay)
    monkeypatch.setattr(outbox_entrypoint, "shutdown_process", fake_shutdown)

    await outbox_entrypoint._run()

    assert calls == ["configure", "object", "shutdown"]


def test_cleanup_worker_main_uses_asyncio_run(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(coro) -> None:
        captured["code_name"] = coro.cr_code.co_name
        coro.close()

    monkeypatch.setattr(cleanup_entrypoint.asyncio, "run", fake_run)
    cleanup_entrypoint.main()

    assert captured["code_name"] == "_run"


def test_enrichment_worker_main_uses_asyncio_run(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(coro) -> None:
        captured["code_name"] = coro.cr_code.co_name
        coro.close()

    monkeypatch.setattr(enrichment_entrypoint.asyncio, "run", fake_run)
    enrichment_entrypoint.main()

    assert captured["code_name"] == "_run"


def test_outbox_worker_main_uses_asyncio_run(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(coro) -> None:
        captured["code_name"] = coro.cr_code.co_name
        coro.close()

    monkeypatch.setattr(outbox_entrypoint.asyncio, "run", fake_run)
    outbox_entrypoint.main()

    assert captured["code_name"] == "_run"
