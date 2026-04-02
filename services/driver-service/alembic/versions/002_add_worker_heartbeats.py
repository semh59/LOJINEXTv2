"""add driver worker heartbeats

Revision ID: 002_add_worker_heartbeats
Revises: 001_initial_schema
Create Date: 2026-04-02 21:51:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "002_add_worker_heartbeats"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "driver_worker_heartbeats",
        sa.Column("worker_name", sa.String(64), nullable=False),
        sa.Column("last_heartbeat_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("worker_status", sa.String(32), nullable=True),
        sa.Column("worker_metadata_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("worker_name"),
    )


def downgrade():
    op.drop_table("driver_worker_heartbeats")
