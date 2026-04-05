"""add trip audit log table

Revision ID: d1e2f3a4b5c6
Revises: c1d2e3f4a5b6
Create Date: 2026-04-05
"""

import sqlalchemy as sa

from alembic import op

revision = "d1e2f3a4b5c6"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trip_audit_log",
        sa.Column("audit_id", sa.String(length=26), primary_key=True),
        sa.Column("trip_id", sa.String(length=26), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("changed_fields_json", sa.Text(), nullable=True),
        sa.Column("old_snapshot_json", sa.Text(), nullable=True),
        sa.Column("new_snapshot_json", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("actor_role", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_trip_audit_trip_created",
        "trip_audit_log",
        ["trip_id", "created_at_utc"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_trip_audit_trip_created", table_name="trip_audit_log")
    op.drop_table("trip_audit_log")
