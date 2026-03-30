"""processing_run_claims

Revision ID: 7b1e9b8b2c6a
Revises: 4d2b8c9e7f10
Create Date: 2026-03-30 21:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7b1e9b8b2c6a"
down_revision: Union[str, None] = "4d2b8c9e7f10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("processing_runs", sa.Column("claim_token", sa.String(length=64), nullable=True))
    op.add_column("processing_runs", sa.Column("claim_expires_at_utc", sa.DateTime(timezone=True), nullable=True))
    op.add_column("processing_runs", sa.Column("claimed_by_worker", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("processing_runs", "claimed_by_worker")
    op.drop_column("processing_runs", "claim_expires_at_utc")
    op.drop_column("processing_runs", "claim_token")
