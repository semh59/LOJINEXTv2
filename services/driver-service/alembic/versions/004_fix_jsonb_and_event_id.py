"""Fix JSONB types and event_id naming.

Revision ID: 004_fix_jsonb_and_event_id
Revises: 003_eda_standardization_v2
Create Date: 2026-04-12
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "004_fix_jsonb_and_event_id"
down_revision = "003_eda_standardization_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Rename outbox_id to event_id to match model
    op.alter_column("driver_outbox", "outbox_id", new_column_name="event_id")

    # 2. Ensure payload_json is treated as JSONB if not already (safeguard)
    # The error said it IS jsonb but expression is varying, meaning model sent string.
    # So we don't need to change type in DB, but we MUST change it in the Model.
    pass


def downgrade() -> None:
    op.alter_column("driver_outbox", "event_id", new_column_name="outbox_id")
