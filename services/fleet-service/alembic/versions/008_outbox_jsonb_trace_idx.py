"""Migrate fleet_outbox payload_json to JSONB and add trace indexes.

Revision ID: 008_outbox_jsonb_trace_idx
Revises: 007_outbox_correlation_id
Create Date: 2026-04-13
"""

from __future__ import annotations

from alembic import op

revision = "008_outbox_jsonb_trace_idx"
down_revision = "007_outbox_correlation_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Convert payload_json back to JSONB
    op.execute("ALTER TABLE fleet_outbox ALTER COLUMN payload_json TYPE JSONB USING payload_json::jsonb")

    # 2. Add indexes for correlation_id and causation_id
    op.create_index("ix_fleet_outbox_correlation", "fleet_outbox", ["correlation_id"])
    op.create_index("ix_fleet_outbox_causation", "fleet_outbox", ["causation_id"])


def downgrade() -> None:
    # 1. Remove indexes
    op.drop_index("ix_fleet_outbox_causation", table_name="fleet_outbox")
    op.drop_index("ix_fleet_outbox_correlation", table_name="fleet_outbox")

    # 2. Convert payload_json back to TEXT
    op.execute("ALTER TABLE fleet_outbox ALTER COLUMN payload_json TYPE TEXT USING payload_json::text")
