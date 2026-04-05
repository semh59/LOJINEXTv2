"""add identity outbox and audit log tables

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
    # identity_outbox
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
        sa.Column("published_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at_utc", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_identity_outbox_pending",
        "identity_outbox",
        ["publish_status", "next_attempt_at_utc", "created_at_utc"],
        unique=False,
    )

    # identity_audit_log
    op.create_table(
        "identity_audit_log",
        sa.Column("audit_id", sa.String(length=26), primary_key=True),
        sa.Column("user_id", sa.String(length=26), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("changed_fields_json", sa.Text(), nullable=True),
        sa.Column("old_snapshot_json", sa.Text(), nullable=True),
        sa.Column("new_snapshot_json", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("actor_role", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_identity_audit_user_created",
        "identity_audit_log",
        ["user_id", "created_at_utc"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_identity_audit_user_created", table_name="identity_audit_log")
    op.drop_table("identity_audit_log")
    # identity_outbox
    op.drop_index("idx_identity_outbox_pending", table_name="identity_outbox")
    op.drop_table("identity_outbox")
