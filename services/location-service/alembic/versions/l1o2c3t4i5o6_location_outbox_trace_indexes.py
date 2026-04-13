"""location outbox trace indexes

Revision ID: l1o2c3t4i5o6
Revises: e1f2a3b4c5d6
Create Date: 2026-04-13
"""

from alembic import op

revision = "l1o2c3t4i5o6"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_location_outbox_correlation", "location_outbox", ["correlation_id"])
    op.create_index("ix_location_outbox_causation", "location_outbox", ["causation_id"])


def downgrade() -> None:
    op.drop_index("ix_location_outbox_causation", table_name="location_outbox")
    op.drop_index("ix_location_outbox_correlation", table_name="location_outbox")
