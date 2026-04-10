"""Driver outbox canonical fields: aggregate_type, aggregate_id, aggregate_version, claim_token, claimed_by_worker.

Revision ID: 68d3e7c9a3d5
Revises: 67d2b6c9a2d4
Create Date: 2026-04-10
"""

from alembic import op
import sqlalchemy as sa

revision = "68d3e7c9a3d5"
down_revision = "67d2b6c9a2d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "driver_outbox",
        sa.Column("aggregate_type", sa.String(16), nullable=False, server_default="DRIVER"),
    )

    op.add_column(
        "driver_outbox",
        sa.Column("aggregate_id", sa.String(26), nullable=False, server_default=""),
    )

    op.add_column(
        "driver_outbox",
        sa.Column("aggregate_version", sa.Integer(), nullable=False, server_default="1"),
    )

    op.add_column(
        "driver_outbox",
        sa.Column("claim_token", sa.String(50), nullable=True),
    )

    op.add_column(
        "driver_outbox",
        sa.Column("claimed_by_worker", sa.String(50), nullable=True),
    )

    op.alter_column(
        "driver_outbox",
        "retry_count",
        new_column_name="attempt_count",
    )

    op.alter_column(
        "driver_outbox",
        "last_error_code",
        type_=sa.String(100),
    )

    op.drop_column("driver_outbox", "last_error")

    op.create_index(
        "ix_driver_outbox_aggregate",
        "driver_outbox",
        ["aggregate_type", "aggregate_id", "created_at_utc"],
    )


def downgrade() -> None:
    op.drop_index("ix_driver_outbox_aggregate", table_name="driver_outbox")

    op.add_column(
        "driver_outbox",
        sa.Column("last_error", sa.Text(), nullable=True),
    )

    op.alter_column(
        "driver_outbox",
        "last_error_code",
        type_=sa.String(64),
    )

    op.alter_column(
        "driver_outbox",
        "attempt_count",
        new_column_name="retry_count",
    )

    op.drop_column("driver_outbox", "claimed_by_worker")
    op.drop_column("driver_outbox", "claim_token")
    op.drop_column("driver_outbox", "aggregate_version")
    op.drop_column("driver_outbox", "aggregate_id")
    op.drop_column("driver_outbox", "aggregate_type")
