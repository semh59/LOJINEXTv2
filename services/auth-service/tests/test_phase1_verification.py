"""Phase 1 Verification Tests ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â Auth Service.

Validates:
  CRITICAL-01: partition_key column exists and is used by HOL blocking query
  CRITICAL-02: correlation_id and causation_id columns exist on AuthOutboxModel
  HIGH-01:     Kafka headers use X-Correlation-ID (not lowercase)
  MED-05:      Dead-letter counter only increments on actual DEAD_LETTER transitions
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect, select, text

from auth_service.models import AuthOutboxModel


# ---------------------------------------------------------------------------
# CRITICAL-01 + CRITICAL-02: Column existence tests
# ---------------------------------------------------------------------------


class TestAuthOutboxSchema:
    """Verify AuthOutboxModel has all required traceability columns."""

    def test_partition_key_column_exists(self):
        """CRITICAL-01: partition_key must exist to prevent HOL blocking crash."""
        mapper = inspect(AuthOutboxModel)
        columns = {c.key for c in mapper.columns}
        assert "partition_key" in columns, (
            "AuthOutboxModel is missing 'partition_key' column ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â "
            "outbox_relay HOL blocking query will crash at runtime"
        )

    def test_partition_key_not_nullable(self):
        """partition_key must NOT be nullable for HOL blocking correctness."""
        mapper = inspect(AuthOutboxModel)
        col = mapper.columns["partition_key"]
        assert not col.nullable, "partition_key must be NOT NULL"

    def test_partition_key_has_default(self):
        """partition_key should default to 'identity' for existing rows."""
        mapper = inspect(AuthOutboxModel)
        col = mapper.columns["partition_key"]
        assert col.default is not None, "partition_key must have a default value"

    def test_correlation_id_column_exists(self):
        """CRITICAL-02: correlation_id must exist for end-to-end tracing."""
        mapper = inspect(AuthOutboxModel)
        columns = {c.key for c in mapper.columns}
        assert "correlation_id" in columns, (
            "AuthOutboxModel is missing 'correlation_id' ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â "
            "events will not be traceable across services"
        )

    def test_causation_id_column_exists(self):
        """CRITICAL-02: causation_id must exist for causal event chains."""
        mapper = inspect(AuthOutboxModel)
        columns = {c.key for c in mapper.columns}
        assert "causation_id" in columns, (
            "AuthOutboxModel is missing 'causation_id' ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â event causation chain will be broken"
        )

    @pytest.mark.asyncio
    async def test_partition_key_materialized_in_database(self, session):
        """Verify partition_key physically exists in the DB table after create_all."""
        result = await session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'auth_outbox' AND column_name = 'partition_key'"
            )
        )
        row = result.scalar_one_or_none()
        assert row == "partition_key", "partition_key column not found in auth_outbox table"

    @pytest.mark.asyncio
    async def test_correlation_id_materialized_in_database(self, session):
        """Verify correlation_id physically exists in the DB table."""
        result = await session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'auth_outbox' AND column_name = 'correlation_id'"
            )
        )
        row = result.scalar_one_or_none()
        assert row == "correlation_id", "correlation_id column not found in auth_outbox table"

    @pytest.mark.asyncio
    async def test_causation_id_materialized_in_database(self, session):
        """Verify causation_id physically exists in the DB table."""
        result = await session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'auth_outbox' AND column_name = 'causation_id'"
            )
        )
        row = result.scalar_one_or_none()
        assert row == "causation_id", "causation_id column not found in auth_outbox table"

    @pytest.mark.asyncio
    async def test_partition_index_exists(self, session):
        """Verify ix_auth_outbox_partition index was created."""
        result = await session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'auth_outbox' AND indexname = 'ix_auth_outbox_partition'"
            )
        )
        row = result.scalar_one_or_none()
        assert row is not None, "ix_auth_outbox_partition index missing"

    @pytest.mark.asyncio
    async def test_outbox_insert_with_traceability_columns(self, session):
        """Full round-trip: insert an outbox row with all new columns, then read it back."""
        now = datetime.now(timezone.utc)
        row = AuthOutboxModel(
            outbox_id="test-outbox-001",
            aggregate_type="User",
            aggregate_id="user-123",
            aggregate_version=1,
            event_name="user.created.v1",
            event_version=1,
            payload_json=json.dumps({"user_id": "user-123"}),
            partition_key="user-123",
            correlation_id="corr-abc-def",
            causation_id="caus-123-456",
            publish_status="PENDING",
            attempt_count=0,
            created_at_utc=now,
            next_attempt_at_utc=now,
        )
        session.add(row)
        await session.commit()

        result = await session.execute(
            select(AuthOutboxModel).where(AuthOutboxModel.outbox_id == "test-outbox-001")
        )
        fetched = result.scalar_one()
        assert fetched.partition_key == "user-123"
        assert fetched.correlation_id == "corr-abc-def"
        assert fetched.causation_id == "caus-123-456"

    @pytest.mark.asyncio
    async def test_hol_blocking_query_compiles_with_partition_key(self, session):
        """CRITICAL-01: The actual HOL blocking query must compile without AttributeError."""
        from sqlalchemy.orm import aliased

        o2 = aliased(AuthOutboxModel)
        # This is the exact query from outbox_relay.py:91-96 that was crashing
        hol_subq = select(1).where(
            o2.partition_key == AuthOutboxModel.partition_key,
            o2.publish_status != "PUBLISHED",
            o2.created_at_utc < AuthOutboxModel.created_at_utc,
        )
        # If partition_key doesn't exist, this will raise AttributeError
        query = (
            select(AuthOutboxModel.outbox_id)
            .where(
                AuthOutboxModel.publish_status == "PENDING",
                ~hol_subq.exists(),
            )
            .limit(10)
        )
        # Execute against real DB ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â should NOT throw
        result = await session.execute(query)
        rows = result.scalars().all()
        assert isinstance(rows, list), "HOL blocking query failed to execute"


# ---------------------------------------------------------------------------
# HIGH-01: Kafka header casing
# ---------------------------------------------------------------------------


class TestAuthBrokerHeaders:
    """Verify identity broker uses standardized X-Correlation-ID header."""

    def test_broker_header_format(self):
        """HIGH-01: Header must be X-Correlation-ID, not x-correlation-id."""
        from pathlib import Path

        broker_path = Path(__file__).parents[1] / "src" / "auth_service" / "broker.py"
        source = broker_path.read_text(encoding="utf-8")

        # Must NOT contain lowercase header
        assert "x-correlation-id" not in source, (
            "broker.py still contains lowercase 'x-correlation-id' header"
        )
        # Must contain standardized header
        assert "X-Correlation-ID" in source, (
            "broker.py missing standardized 'X-Correlation-ID' header"
        )

    def test_causation_id_header_propagated(self):
        """HIGH-01 extension: X-Causation-ID header must be propagated."""
        from pathlib import Path

        broker_path = Path(__file__).parents[1] / "src" / "auth_service" / "broker.py"
        source = broker_path.read_text(encoding="utf-8")
        assert "X-Causation-ID" in source, "broker.py missing X-Causation-ID header propagation"


# ---------------------------------------------------------------------------
# MED-05: Dead-letter counter fix
# ---------------------------------------------------------------------------


class TestDeadLetterCounterAccuracy:
    """Verify DLQ counter only increments on actual DEAD_LETTER transitions."""

    def test_dead_letter_counter_code_pattern(self):
        """MED-05: Counter must check publish_status == 'DEAD_LETTER', not row_data is None."""
        from pathlib import Path

        relay_path = (
            Path(__file__).parents[1] / "src" / "auth_service" / "workers" / "outbox_relay.py"
        )
        source = relay_path.read_text(encoding="utf-8")

        # Old buggy pattern: check if row_data is None
        assert "row_data = await _load_claimed_payload" not in source.split("except")[-1], (
            "Dead-letter counter still uses old buggy _load_claimed_payload pattern"
        )

        # New correct pattern: check publish_status
        assert 'publish_status == "DEAD_LETTER"' in source, (
            "Dead-letter counter must check for actual DEAD_LETTER status"
        )
