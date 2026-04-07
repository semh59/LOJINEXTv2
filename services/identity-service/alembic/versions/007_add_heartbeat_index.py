"""add index to identity worker heartbeats

Revision ID: 007_add_heartbeat_index
Revises: 006_harden_outbox_schema
Create Date: 2026-04-07
"""

from alembic import op


revision = "007_add_heartbeat_index"
down_revision = "006_harden_outbox_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_identity_worker_heartbeats_last_seen",
        "identity_worker_heartbeats",
        ["last_seen_at_utc"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_identity_worker_heartbeats_last_seen",
        table_name="identity_worker_heartbeats",
    )
