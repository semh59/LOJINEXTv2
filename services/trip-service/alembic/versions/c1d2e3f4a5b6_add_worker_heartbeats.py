"""add worker heartbeats

Revision ID: c1d2e3f4a5b6
Revises: b2c3d4e5f6a1
Create Date: 2026-04-02 21:45:00
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "b2c3d4e5f6a1"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_name", sa.String(length=100), nullable=False),
        sa.Column("recorded_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("worker_name"),
    )


def downgrade() -> None:
    op.drop_table("worker_heartbeats")
