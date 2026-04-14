"""Add correlation_id to fleet_outbox.

Revision ID: 007_outbox_correlation_id
Revises: 4182cecbfaad
Create Date: 2026-04-12
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "007_outbox_correlation_id"
down_revision = "4182cecbfaad"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fleet_outbox",
        sa.Column("correlation_id", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("fleet_outbox", "correlation_id")
