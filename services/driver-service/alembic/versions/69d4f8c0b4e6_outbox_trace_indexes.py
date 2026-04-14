"""driver outbox trace indexes

Revision ID: 69d4f8c0b4e6
Revises: 68d3e7c9a3d5
Create Date: 2026-04-13
"""

from alembic import op

revision = "69d4f8c0b4e6"
down_revision = "68d3e7c9a3d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    import sqlalchemy as sa
    op.add_column("driver_outbox", sa.Column("correlation_id", sa.String(length=64), nullable=True))
    op.add_column("driver_outbox", sa.Column("causation_id", sa.String(length=64), nullable=True))
    op.create_index("ix_driver_outbox_correlation", "driver_outbox", ["correlation_id"])
    op.create_index("ix_driver_outbox_causation", "driver_outbox", ["causation_id"])


def downgrade() -> None:
    op.drop_index("ix_driver_outbox_causation", table_name="driver_outbox")
    op.drop_index("ix_driver_outbox_correlation", table_name="driver_outbox")
    op.drop_column("driver_outbox", "correlation_id")
    op.drop_column("driver_outbox", "causation_id")
