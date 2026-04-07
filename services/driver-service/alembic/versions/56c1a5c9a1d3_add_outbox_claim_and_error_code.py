"""add_outbox_claim_and_error_code

Revision ID: 56c1a5c9a1d3
Revises: 002_add_worker_heartbeats
Create Date: 2026-04-07 14:12:17.257298

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "56c1a5c9a1d3"
down_revision: Union[str, None] = "002_add_worker_heartbeats"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add new columns
    op.add_column("driver_outbox", sa.Column("last_error_code", sa.String(length=64), nullable=True))
    op.add_column("driver_outbox", sa.Column("claim_expires_at_utc", sa.DateTime(timezone=True), nullable=True))

    # 2. Update check constraint for status
    # First drop old one
    op.drop_constraint("ck_driver_outbox_status_valid", "driver_outbox", type_="check")
    # Add new one including PUBLISHING
    op.create_check_constraint(
        "ck_driver_outbox_status_valid",
        "driver_outbox",
        "publish_status IN ('PENDING', 'PUBLISHING', 'PUBLISHED', 'FAILED', 'DEAD_LETTER')",
    )


def downgrade() -> None:
    # 1. Revert check constraint
    op.drop_constraint("ck_driver_outbox_status_valid", "driver_outbox", type_="check")
    op.create_check_constraint(
        "ck_driver_outbox_status_valid",
        "driver_outbox",
        "publish_status IN ('PENDING', 'PUBLISHED', 'FAILED', 'DEAD_LETTER')",
    )

    # 2. Remove columns
    op.drop_column("driver_outbox", "claim_expires_at_utc")
    op.drop_column("driver_outbox", "last_error_code")
