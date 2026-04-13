"""trip outbox payload_json text alignment

Revision ID: a9c8e7f6d5b4
Revises: f1a2b3c4d5e6
Create Date: 2026-04-11
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "a9c8e7f6d5b4"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "trip_outbox",
        "payload_json",
        existing_type=postgresql.JSONB(),
        type_=sa.Text(),
        postgresql_using="payload_json::text",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "trip_outbox",
        "payload_json",
        existing_type=sa.Text(),
        type_=postgresql.JSONB(),
        postgresql_using="payload_json::jsonb",
        existing_nullable=False,
    )
