"""outbox_claim

Revision ID: 1a2b3c4d5e6f
Revises: 0d5f12e97db6
Create Date: 2026-04-07 12:45:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1a2b3c4d5e6f"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("location_outbox", sa.Column("last_error_code", sa.String(length=100), nullable=True))
    op.add_column("location_outbox", sa.Column("claim_expires_at_utc", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("location_outbox", "claim_expires_at_utc")
    op.drop_column("location_outbox", "last_error_code")
