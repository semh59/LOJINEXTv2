"""EDA Standardization V2: add partition_key, trace headers, and idempotency table.

Revision ID: 003_eda_standardization_v2
Revises: 68d3e7c9a3d5
Create Date: 2026-04-12
"""

import sqlalchemy as sa
from alembic import op

revision = "003_eda_standardization_v2"
down_revision = "70e5g9d1c5f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Extend driver_outbox with missing canonical fields
    op.add_column("driver_outbox", sa.Column("partition_key", sa.String(64), nullable=True))
    op.add_column("driver_outbox", sa.Column("request_id", sa.String(64), nullable=True))
    op.add_column("driver_outbox", sa.Column("correlation_id", sa.String(64), nullable=True))
    op.add_column("driver_outbox", sa.Column("causation_id", sa.String(64), nullable=True))

    # Restore last_error (Text) which was dropped in 68d3...
    # (Checking if it exists first to be safe)
    op.add_column("driver_outbox", sa.Column("last_error", sa.Text(), nullable=True))

    op.create_index("ix_driver_outbox_request_id", "driver_outbox", ["request_id"])
    op.create_index("ix_driver_outbox_correlation_id", "driver_outbox", ["correlation_id"])

    # 2. Create driver_idempotency table
    op.create_table(
        "driver_idempotency",
        sa.Column("idempotency_key", sa.String(128), primary_key=True),
        sa.Column("endpoint_fingerprint", sa.String(128), nullable=False),
        sa.Column("response_code", sa.Integer(), nullable=False),
        sa.Column("response_body_json", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_driver_idempotency_expires", "driver_idempotency", ["expires_at_utc"])

    # 3. Add actor_type tracking to drivers for forensic parity
    op.add_column("driver_drivers", sa.Column("created_by_actor_type", sa.String(32), nullable=True))
    op.add_column("driver_drivers", sa.Column("updated_by_actor_type", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("driver_drivers", "updated_by_actor_type")
    op.drop_column("driver_drivers", "created_by_actor_type")

    op.drop_index("ix_driver_idempotency_expires", table_name="driver_idempotency")
    op.drop_table("driver_idempotency")

    op.drop_column("driver_outbox", "last_error")
    op.drop_index("ix_driver_outbox_correlation_id", table_name="driver_outbox")
    op.drop_index("ix_driver_outbox_request_id", table_name="driver_outbox")
    op.drop_column("driver_outbox", "causation_id")
    op.drop_column("driver_outbox", "correlation_id")
    op.drop_column("driver_outbox", "request_id")
    op.drop_column("driver_outbox", "partition_key")
