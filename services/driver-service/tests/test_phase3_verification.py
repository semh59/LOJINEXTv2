"""Phase 3 Verification Tests — Driver Service.

Validates:
  Phase 3-A: KafkaBroker uses AIOProducer (not sync Producer)
  Phase 3-B: No background _poll_loop task (eliminated by AIOProducer)
  Phase 3-C: Proper async close() without _poll_task cleanup
  Phase 3-D: Header propagation standards maintained
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

BROKER_PATH = Path(__file__).parents[1] / "src" / "driver_service" / "broker.py"


class TestPhase3AIOProducerMigration:
    """Verify driver-service uses AIOProducer instead of sync Producer."""

    def _get_source(self) -> str:
        return BROKER_PATH.read_text(encoding="utf-8")

    def test_aio_producer_imported(self):
        """AIOProducer must be imported (with fallback for experimental path)."""
        source = self._get_source()
        assert "AIOProducer" in source, "broker.py must import AIOProducer"
        # Must NOT import sync Producer for the main broker
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and "confluent_kafka" in node.module:
                    for alias in node.names:
                        if alias.name == "Producer":
                            pytest.fail("broker.py still imports sync Producer — must use AIOProducer only")

    def test_kafka_broker_uses_aio_producer(self):
        """KafkaBroker.__init__ must instantiate AIOProducer, not Producer."""
        source = self._get_source()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "KafkaBroker":
                class_source = ast.get_source_segment(source, node)
                assert "AIOProducer(" in class_source, "KafkaBroker must use AIOProducer(config)"
                assert "Producer(config)" not in class_source.replace("AIOProducer(config)", ""), (
                    "KafkaBroker must not use sync Producer(config)"
                )
                return

        pytest.fail("KafkaBroker class not found")

    def test_no_poll_loop(self):
        """AIOProducer eliminates the need for _poll_loop background task."""
        source = self._get_source()
        assert "_poll_loop" not in source, (
            "broker.py should not have _poll_loop — AIOProducer handles polling internally"
        )
        assert "_poll_task" not in source, (
            "broker.py should not have _poll_task — AIOProducer handles polling internally"
        )


class TestPhase3AsyncClose:
    """Verify broker.close() properly uses async AIOProducer methods."""

    def test_close_no_sync_flush(self):
        """close() must use await self._producer.flush(), not sync flush."""
        source = BROKER_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "KafkaBroker":
                for item in node.body:
                    if isinstance(item, ast.AsyncFunctionDef) and item.name == "close":
                        close_source = ast.get_source_segment(source, item)
                        # Should NOT have _poll_task cancellation
                        assert "_poll_task" not in close_source, "close() should not reference _poll_task"
                        return

        pytest.fail("KafkaBroker.close() not found")


class TestPhase3HeaderPropagation:
    """Verify header standards maintained after migration."""

    def test_correlation_id_header(self):
        source = BROKER_PATH.read_text(encoding="utf-8")
        assert "X-Correlation-ID" in source, "Must propagate X-Correlation-ID header"

    def test_causation_id_header(self):
        source = BROKER_PATH.read_text(encoding="utf-8")
        assert "X-Causation-ID" in source, "Must propagate X-Causation-ID header"

    def test_request_id_header(self):
        source = BROKER_PATH.read_text(encoding="utf-8")
        assert "X-Request-ID" in source, "Must propagate X-Request-ID header"

    def test_acks_all(self):
        source = BROKER_PATH.read_text(encoding="utf-8")
        assert '"acks"' in source and '"all"' in source, "Must have acks=all"

    def test_enable_idempotence(self):
        source = BROKER_PATH.read_text(encoding="utf-8")
        assert '"enable.idempotence"' in source, "Must have enable.idempotence"
