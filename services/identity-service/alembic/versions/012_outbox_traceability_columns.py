"""Add partition_key, correlation_id, causation_id to identity_outbox.

Revision ID: 012_outbox_traceability_columns
Revises: 011_outbox_canonical_fields
Create Date: 2026-04-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "012_outbox_traceability_columns"
down_revision = "011_outbox_canonical_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- partition_key: required for HOL blocking ---
    op.add_column(
        "identity_outbox",
        sa.Column(
            "partition_key",
            sa.String(100),
            nullable=False,
            server_default="identity",
        ),
    )

    # --- correlation_id: end-to-end request tracing ---
    op.add_column(
        "identity_outbox",
        sa.Column("correlation_id", sa.String(64), nullable=True),
    )

    # --- causation_id: causal event chain ---
    op.add_column(
        "identity_outbox",
        sa.Column("causation_id", sa.String(64), nullable=True),
    )

    # --- composite index for relay partition-key ordering ---
    op.create_index(
        "ix_identity_outbox_partition",
        "identity_outbox",
        ["partition_key", "publish_status", "created_at_utc"],
    )


def downgrade() -> None:
    op.drop_index("ix_identity_outbox_partition", table_name="identity_outbox")
    op.drop_column("identity_outbox", "causation_id")
    op.drop_column("identity_outbox", "correlation_id")
    op.drop_column("identity_outbox", "partition_key")
