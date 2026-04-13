"""identity outbox trace indexes

Revision ID: 013_outbox_trace_indexes
Revises: 012_outbox_traceability_columns
Create Date: 2026-04-13
"""

from alembic import op

revision = "013_outbox_trace_indexes"
down_revision = "012_outbox_traceability_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_identity_outbox_correlation", "identity_outbox", ["correlation_id"])
    op.create_index("ix_identity_outbox_causation", "identity_outbox", ["causation_id"])


def downgrade() -> None:
    op.drop_index("ix_identity_outbox_causation", table_name="identity_outbox")
    op.drop_index("ix_identity_outbox_correlation", table_name="identity_outbox")
