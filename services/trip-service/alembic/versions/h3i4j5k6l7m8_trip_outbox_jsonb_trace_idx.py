"""trip outbox JSONB and trace indexes

Revision ID: h3i4j5k6l7m8
Revises: g2h3i4j5k6l7
Create Date: 2026-04-13
"""

from alembic import op

revision = "h3i4j5k6l7m8"
down_revision = "g2h3i4j5k6l7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Cast payload_json back to JSONB
    op.execute("ALTER TABLE trip_outbox ALTER COLUMN payload_json TYPE JSONB USING payload_json::jsonb")

    import sqlalchemy as sa
    # 2. Add Trace IDs
    op.add_column("trip_outbox", sa.Column("correlation_id", sa.String(64), nullable=True))
    op.add_column("trip_outbox", sa.Column("causation_id", sa.String(64), nullable=True))

    # 3. Add trace indexes
    op.create_index("ix_trip_outbox_correlation", "trip_outbox", ["correlation_id"])
    op.create_index("ix_trip_outbox_causation", "trip_outbox", ["causation_id"])


def downgrade() -> None:
    # 1. Remove indexes
    op.drop_index("ix_trip_outbox_causation", table_name="trip_outbox")
    op.drop_index("ix_trip_outbox_correlation", table_name="trip_outbox")
    op.drop_column("trip_outbox", "causation_id")
    op.drop_column("trip_outbox", "correlation_id")

    # 2. Revert to TEXT
    op.execute("ALTER TABLE trip_outbox ALTER COLUMN payload_json TYPE TEXT USING payload_json::text")
