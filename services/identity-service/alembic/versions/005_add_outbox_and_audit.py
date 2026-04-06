"""add identity outbox, audit log, and worker heartbeat tables

Revision ID: 005_add_outbox_and_audit
Revises: 004_drop_plaintext_signing_key
Create Date: 2026-04-05
"""

from alembic import op
import sqlalchemy as sa


revision = "005_add_outbox_and_audit"
down_revision = "004_drop_plaintext_signing_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "identity_outbox",
        sa.Column("outbox_id", sa.String(length=26), primary_key=True),
        sa.Column("aggregate_type", sa.String(length=32), nullable=False),
        sa.Column("aggregate_id", sa.String(length=26), nullable=False),
        sa.Column("event_name", sa.String(length=128), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column(
            "publish_status",
            sa.String(length=32),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claim_expires_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["aggregate_id"], ["identity_users.user_id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "idx_identity_outbox_pending",
        "identity_outbox",
        ["publish_status", "next_attempt_at_utc", "created_at_utc"],
        unique=False,
    )
    op.create_index(
        "idx_identity_outbox_aggregate",
        "identity_outbox",
        ["aggregate_type", "aggregate_id", "created_at_utc"],
        unique=False,
    )

    op.create_table(
        "identity_audit_log",
        sa.Column("audit_id", sa.String(length=26), primary_key=True),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=26), nullable=True),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("actor_role", sa.String(length=64), nullable=False),
        sa.Column("old_snapshot_json", sa.Text(), nullable=True),
        sa.Column("new_snapshot_json", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["target_id"], ["identity_users.user_id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "idx_identity_audit_target_created",
        "identity_audit_log",
        ["target_type", "target_id", "created_at_utc"],
        unique=False,
    )

    op.create_table(
        "identity_worker_heartbeats",
        sa.Column("worker_name", sa.String(length=64), primary_key=True),
        sa.Column("last_seen_at_utc", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("identity_worker_heartbeats")
    op.drop_index("idx_identity_audit_target_created", table_name="identity_audit_log")
    op.drop_table("identity_audit_log")
    op.drop_index("idx_identity_outbox_aggregate", table_name="identity_outbox")
    op.drop_index("idx_identity_outbox_pending", table_name="identity_outbox")
    op.drop_table("identity_outbox")
