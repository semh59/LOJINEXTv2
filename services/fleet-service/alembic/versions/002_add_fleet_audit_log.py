"""add fleet audit log table

Revision ID: 002_add_fleet_audit_log
Revises: 001_schema_bootstrap
Create Date: 2026-04-05
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "002_add_fleet_audit_log"
down_revision = "001_schema_bootstrap"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fleet_audit_log",
        sa.Column("audit_id", sa.String(length=26), primary_key=True),
        sa.Column("aggregate_type", sa.String(length=16), nullable=False),
        sa.Column("aggregate_id", sa.String(length=26), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("changed_fields_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("old_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("actor_role", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_fleet_audit_agg_created",
        "fleet_audit_log",
        ["aggregate_type", "aggregate_id", "created_at_utc"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_fleet_audit_agg_created", table_name="fleet_audit_log")
    op.drop_table("fleet_audit_log")
