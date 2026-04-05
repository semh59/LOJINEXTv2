"""add worker heartbeats

Revision ID: e5f6a1b2c3d4
Revises: 7b1e9b8b2c6a
Create Date: 2026-04-02 21:50:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a1b2c3d4"
down_revision: Union[str, None] = "7b1e9b8b2c6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_name", sa.String(length=100), nullable=False),
        sa.Column("recorded_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("worker_name"),
    )


def downgrade() -> None:
    op.drop_table("worker_heartbeats")
