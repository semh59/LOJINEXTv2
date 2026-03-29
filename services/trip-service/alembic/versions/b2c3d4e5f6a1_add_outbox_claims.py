"""add outbox claims

Revision ID: b2c3d4e5f6a1
Revises: a1b2c3d4e5f6
Create Date: 2026-03-28 17:40:00
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b2c3d4e5f6a1"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trip_outbox", sa.Column("claim_token", sa.String(length=50), nullable=True))
    op.add_column("trip_outbox", sa.Column("claim_expires_at_utc", sa.DateTime(timezone=True), nullable=True))
    op.add_column("trip_outbox", sa.Column("claimed_by_worker", sa.String(length=50), nullable=True))
    op.create_index("ix_outbox_claim_exp", "trip_outbox", ["claim_expires_at_utc"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_outbox_claim_exp", table_name="trip_outbox")
    op.drop_column("trip_outbox", "claimed_by_worker")
    op.drop_column("trip_outbox", "claim_expires_at_utc")
    op.drop_column("trip_outbox", "claim_token")
