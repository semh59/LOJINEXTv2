"""add encrypted signing key columns

Revision ID: 002_add_signing_key_ciphertext_columns
Revises: 001_initial_schema
Create Date: 2026-04-05
"""

from alembic import op
import sqlalchemy as sa


revision = "002_add_signing_key_ciphertext_columns"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "identity_signing_keys",
        sa.Column("private_key_ciphertext_b64", sa.Text(), nullable=True),
    )
    op.add_column(
        "identity_signing_keys",
        sa.Column("private_key_kek_version", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("identity_signing_keys", "private_key_kek_version")
    op.drop_column("identity_signing_keys", "private_key_ciphertext_b64")
