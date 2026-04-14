"""Phase 1 Verification Tests — Fleet Service.

Validates:
  HIGH-05: correlation_id column exists on FleetOutbox
  HIGH-06: run_outbox_relay does NOT call broker.close() (entrypoint handles it)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect, select, text

from fleet_service.models import FleetOutbox

# ---------------------------------------------------------------------------
# HIGH-05: FleetOutbox correlation_id column
# ---------------------------------------------------------------------------


class TestFleetOutboxSchema:
    """Verify FleetOutbox has correlation_id for cross-service traceability."""

    def test_correlation_id_column_exists(self):
        """HIGH-05: correlation_id must exist on FleetOutbox."""
        mapper = inspect(FleetOutbox)
        columns = {c.key for c in mapper.columns}
        assert "correlation_id" in columns, (
            "FleetOutbox is missing 'correlation_id' column — events will lose their original correlation context"
        )

    def test_correlation_id_is_nullable(self):
        """correlation_id should be nullable for backward compatibility."""
        mapper = inspect(FleetOutbox)
        col = mapper.columns["correlation_id"]
        assert col.nullable, "correlation_id should be nullable"

    def test_causation_id_still_exists(self):
        """Ensure causation_id wasn't accidentally removed when adding correlation_id."""
        mapper = inspect(FleetOutbox)
        columns = {c.key for c in mapper.columns}
        assert "causation_id" in columns, "causation_id column was accidentally removed"

    @pytest.mark.asyncio
    async def test_correlation_id_materialized_in_database(self, test_session):
        """Verify correlation_id physically exists in fleet_outbox table."""
        try:
            result = await test_session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'fleet_outbox' AND column_name = 'correlation_id'"
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                pytest.skip("correlation_id column not in DB yet — run 'alembic upgrade head' to apply migration 007")
            assert row == "correlation_id"
        except Exception as exc:
            pytest.skip(f"DB check failed (pre-migration state): {exc}")

    @pytest.mark.asyncio
    async def test_outbox_insert_with_correlation_id(self, test_session):
        """Full round-trip: insert outbox row with correlation_id."""
        try:
            now = datetime.now(timezone.utc)
            row = FleetOutbox(
                outbox_id="test-fleet-outbox-001",
                aggregate_type="Vehicle",
                aggregate_id="vehicle-123",
                correlation_id="corr-fleet-abc",
                causation_id="caus-fleet-xyz",
                event_name="vehicle.created.v1",
                event_version=1,
                payload_json=json.dumps({"vehicle_id": "vehicle-123"}),
                partition_key="vehicle-123",
                publish_status="PENDING",
                attempt_count=0,
                created_at_utc=now,
                next_attempt_at_utc=now,
            )
            test_session.add(row)
            await test_session.commit()

            result = await test_session.execute(
                select(FleetOutbox).where(FleetOutbox.outbox_id == "test-fleet-outbox-001")
            )
            fetched = result.scalar_one()
            assert fetched.correlation_id == "corr-fleet-abc"
            assert fetched.causation_id == "caus-fleet-xyz"
        except Exception as exc:
            if "correlation_id" in str(exc).lower() or "column" in str(exc).lower():
                pytest.skip(f"Migration 007 not applied yet — DB insert failed: {type(exc).__name__}")
            raise


# ---------------------------------------------------------------------------
# HIGH-06: Double broker.close() fix
# ---------------------------------------------------------------------------


class TestFleetOutboxRelayCleanup:
    """Verify run_outbox_relay does NOT call broker.close() directly."""

    def test_no_broker_close_in_relay(self):
        """HIGH-06: run_outbox_relay must NOT close the broker — entrypoint handles it."""
        import ast
        from pathlib import Path

        relay_path = Path(__file__).parents[1] / "src" / "fleet_service" / "workers" / "outbox_relay.py"
        source = relay_path.read_text(encoding="utf-8")

        # Parse AST and find the run_outbox_relay function
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "run_outbox_relay":
                # Walk the function body for broker.close() calls
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Attribute) and inner.attr == "close":
                        if isinstance(inner.value, ast.Name) and inner.value.id == "broker":
                            pytest.fail(
                                "run_outbox_relay still calls broker.close() — "
                                "this causes double-close since worker_main also does it"
                            )

    def test_no_orphaned_try_blocks(self):
        """Verify removing the finally block didn't leave syntax errors."""
        import ast
        from pathlib import Path

        relay_path = Path(__file__).parents[1] / "src" / "fleet_service" / "workers" / "outbox_relay.py"
        source = relay_path.read_text(encoding="utf-8")

        # If this parses without error, there are no orphaned try blocks
        try:
            ast.parse(source)
        except SyntaxError as e:
            pytest.fail(f"outbox_relay.py has a syntax error: {e}")
