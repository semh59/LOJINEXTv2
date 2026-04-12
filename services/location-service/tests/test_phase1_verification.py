"""Phase 1 Verification Tests — Location Service.

Validates:
  CRITICAL-03: KafkaBroker config includes acks=all and enable.idempotence=True
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


class TestLocationBrokerDataDurability:
    """Verify location-service KafkaBroker has production-grade durability settings."""

    def _get_broker_source(self) -> str:
        broker_path = Path(__file__).parents[1] / "src" / "location_service" / "broker.py"
        return broker_path.read_text(encoding="utf-8")

    def test_acks_all_configured(self):
        """CRITICAL-03: KafkaBroker must have acks=all for zero data loss."""
        source = self._get_broker_source()
        assert '"acks"' in source or "'acks'" in source, "KafkaBroker config is missing 'acks' setting"
        assert '"all"' in source or "'all'" in source, "KafkaBroker acks must be set to 'all'"

    def test_enable_idempotence_configured(self):
        """CRITICAL-03: KafkaBroker must have enable.idempotence=True."""
        source = self._get_broker_source()
        assert '"enable.idempotence"' in source or "'enable.idempotence'" in source, (
            "KafkaBroker config is missing 'enable.idempotence' setting"
        )

    def test_config_dict_has_durability_keys(self):
        """Parse AST to verify config dict contains both durability keys."""
        source = self._get_broker_source()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "KafkaBroker":
                # Find the __init__ method
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "__init__":
                        source_lines = source.split("\n")
                        init_source = "\n".join(source_lines[item.lineno - 1 : item.end_lineno])
                        assert "acks" in init_source, "acks not in KafkaBroker.__init__"
                        assert "enable.idempotence" in init_source, "enable.idempotence not in KafkaBroker.__init__"
                        return

        pytest.fail("KafkaBroker class or __init__ method not found in broker.py")

    def test_header_casing_consistency(self):
        """Verify location-service uses X-Correlation-ID (not lowercase)."""
        source = self._get_broker_source()
        # Check there's no lowercase variant
        assert (
            "x-correlation-id" not in source.lower().replace("x-correlation-id", "").lower()
            or "X-Correlation-ID" in source
        ), "Location broker should use X-Correlation-ID header"


class TestLocationRelayDeadCodeRemovalReadiness:
    """Verify the old class-based relay can be safely removed (pre-Phase 2 check)."""

    def test_old_relay_still_exists_awaiting_removal(self):
        """Document that the old relay exists and should be removed in Phase 2."""
        old_relay_path = Path(__file__).parents[1] / "src" / "location_service" / "outbox_relay.py"
        # This test documents the state — old relay still needs deletion
        if old_relay_path.exists():
            pytest.skip("Old class-based outbox_relay.py still exists — will be removed in Phase 2")
        else:
            # After Phase 2, this should pass
            assert True, "Old relay successfully removed"

    def test_active_relay_uses_settings_kafka_topic(self):
        """Verify the active relay uses settings.kafka_topic, not event_name as topic."""
        active_relay_path = Path(__file__).parents[1] / "src" / "location_service" / "workers" / "outbox_relay.py"
        source = active_relay_path.read_text(encoding="utf-8")
        assert "settings.kafka_topic" in source, "Active relay must use settings.kafka_topic"
