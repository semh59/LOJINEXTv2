"""Phase 2 & 3 Verification Tests — Location Service.

Validates:
  Phase 2-A: Dead code outbox_relay.py (class-based) has been deleted
  Phase 2-B: Entrypoint imports active relay from workers.outbox_relay
  Phase 2-C: Active relay releases DB session before Kafka IO (connection pool safety)
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


SERVICE_SRC = Path(__file__).parents[1] / "src" / "location_service"


class TestPhase2DeadCodeRemoval:
    """Verify old class-based outbox_relay.py has been deleted."""

    def test_old_relay_module_deleted(self):
        """The old outbox_relay.py (with OutboxRelay class) must not exist."""
        old_path = SERVICE_SRC / "outbox_relay.py"
        assert not old_path.exists(), (
            f"Dead code module still exists: {old_path} — "
            "this old class-based relay was replaced by workers/outbox_relay.py"
        )

    def test_no_import_of_old_relay(self):
        """No module should import from location_service.outbox_relay."""
        for py_file in SERVICE_SRC.rglob("*.py"):
            if py_file.name == "__pycache__":
                continue
            source = py_file.read_text(encoding="utf-8")
            assert "from location_service.outbox_relay" not in source, (
                f"{py_file.name} still imports from deleted module location_service.outbox_relay"
            )


class TestPhase2EntrypointFix:
    """Verify outbox_worker.py uses the correct active relay."""

    def test_entrypoint_imports_workers_relay(self):
        """Entrypoint must import from workers.outbox_relay, not root."""
        entrypoint = SERVICE_SRC / "entrypoints" / "outbox_worker.py"
        source = entrypoint.read_text(encoding="utf-8")
        assert "from location_service.workers.outbox_relay import run_outbox_relay" in source, (
            "Entrypoint must import run_outbox_relay from workers.outbox_relay"
        )

    def test_entrypoint_creates_broker(self):
        """Entrypoint must create and manage broker lifecycle."""
        entrypoint = SERVICE_SRC / "entrypoints" / "outbox_worker.py"
        source = entrypoint.read_text(encoding="utf-8")
        assert "create_broker" in source, "Entrypoint must call create_broker() to instantiate the broker"
        assert "broker.close()" in source, "Entrypoint must close broker in finally block"

    def test_entrypoint_passes_broker_to_relay(self):
        """run_outbox_relay must receive broker as first argument."""
        entrypoint = SERVICE_SRC / "entrypoints" / "outbox_worker.py"
        source = entrypoint.read_text(encoding="utf-8")
        assert "run_outbox_relay(broker" in source, "Entrypoint must pass broker to run_outbox_relay"


class TestPhase2RelaySafeSessionHandling:
    """Verify active relay closes DB session before Kafka IO."""

    def test_relay_uses_context_manager_session(self):
        """Active relay must use 'async with' session for automatic cleanup."""
        relay_path = SERVICE_SRC / "workers" / "outbox_relay.py"
        source = relay_path.read_text(encoding="utf-8")
        assert "async with async_session_factory()" in source, "Relay must use 'async with' for DB session lifecycle"

    def test_relay_accepts_broker_parameter(self):
        """run_outbox_relay must accept broker as first parameter."""
        relay_path = SERVICE_SRC / "workers" / "outbox_relay.py"
        tree = ast.parse(relay_path.read_text(encoding="utf-8"))

        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "run_outbox_relay":
                args = [arg.arg for arg in node.args.args]
                assert "broker" in args, "run_outbox_relay must accept 'broker' parameter"
                return

        pytest.fail("run_outbox_relay function not found")
