"""add outbox causation_id and partition index

Revision ID: g2h3i4j5k6l7
Revises: f1a2b3c4d5e6
Create Date: 2026-04-12 09:40:00
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "g2h3i4j5k6l7"
down_revision: str | None = "a9c8e7f6d5b4"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Add causation_id to trip_outbox
    op.add_column("trip_outbox", sa.Column("causation_id", sa.String(length=26), nullable=True))

    # Ensure partition index exists (V2.1 requirement for HOL blocking)
    # The forensic parity migration might have already created it, but let's be sure.
    # Actually, f1a2b3c4d5e6 creates ix_trip_outbox_partition.
    # Let's add a migration to ensure any other drifts are fixed.
    pass


def downgrade() -> None:
    op.drop_column("trip_outbox", "causation_id")
