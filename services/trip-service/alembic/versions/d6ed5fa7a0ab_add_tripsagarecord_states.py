"""Add TripSagaRecord states

Revision ID: d6ed5fa7a0ab
Revises: i4j5k6l7m8n9
Create Date: 2026-04-13 13:02:28.563756
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision: str = "d6ed5fa7a0ab"
down_revision: Union[str, None] = "i4j5k6l7m8n9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trip_saga_states",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("trip_id", sa.String(length=26), nullable=False),
        sa.Column("saga_status", sa.String(length=50), nullable=False),
        sa.Column("current_step", sa.String(length=100), nullable=False),
        sa.Column("failures_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at_utc",
            sa.DateTime(timezone=True),
            server_default=sa.text("timezone('utc', now())"),
            nullable=False,
        ),
        sa.Column(
            "updated_at_utc",
            sa.DateTime(timezone=True),
            server_default=sa.text("timezone('utc', now())"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["trip_trips.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trip_id"),
    )


def downgrade() -> None:
    op.drop_table("trip_saga_states")
