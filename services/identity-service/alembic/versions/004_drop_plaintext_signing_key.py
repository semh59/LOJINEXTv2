"""drop plaintext signing key column

Revision ID: 004_drop_plaintext_signing_key
Revises: 003_backfill_signing_key_ciphertext
Create Date: 2026-04-05
"""

from alembic import op
import sqlalchemy as sa


revision = "004_drop_plaintext_signing_key"
down_revision = "003_backfill_signing_key_ciphertext"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("identity_signing_keys", "private_key_ciphertext_b64", existing_type=sa.Text(), nullable=False)
    op.alter_column("identity_signing_keys", "private_key_kek_version", existing_type=sa.String(length=64), nullable=False)
    op.drop_column("identity_signing_keys", "private_key_pem")


def downgrade() -> None:
    op.add_column("identity_signing_keys", sa.Column("private_key_pem", sa.Text(), nullable=True))
