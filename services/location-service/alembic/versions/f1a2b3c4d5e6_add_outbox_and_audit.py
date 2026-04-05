"""add location outbox and audit log tables

Revision ID: f1a2b3c4d5e6
Revises: e5f6a1b2c3d4
Create Date: 2026-04-05
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e5f6a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # location_outbox
    op.create_table(
        "location_outbox",
        sa.Column("outbox_id", sa.String(length=26), primary_key=True),
        sa.Column("event_name", sa.String(length=64), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("publish_status", sa.String(length=16), nullable=False, server_default="PENDING"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at_utc", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_location_outbox_pending",
        "location_outbox",
        ["publish_status", "next_attempt_at_utc", "created_at_utc"],
        unique=False,
    )

    # location_audit_log
    op.create_table(
        "location_audit_log",
        sa.Column("audit_id", sa.String(length=26), primary_key=True),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("actor_role", sa.String(length=32), nullable=False),
        sa.Column("old_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_location_audit_target",
        "location_audit_log",
        ["target_type", "target_id", "created_at_utc"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_location_audit_target", table_name="location_audit_log")
    op.drop_table("location_audit_log")
    op.drop_index("idx_location_outbox_pending", table_name="location_outbox")
    op.drop_table("location_outbox")
