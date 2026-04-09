"""Security hardening: refresh token family tracking, user deactivated_at_utc.

Revision ID: 010_security_hardening
Revises: 009_final_forensic_parity
Create Date: 2026-04-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "010_security_hardening"
down_revision = "009_final_forensic_parity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add family_id to identity_refresh_tokens for token-family reuse detection
    op.add_column(
        "identity_refresh_tokens",
        sa.Column("family_id", sa.String(26), nullable=True),
    )

    # 2. Invalidate all legacy tokens that have no family_id (active sessions).
    #    These tokens cannot participate in family-revocation tracking.
    #    Users will need to log in again after this migration.
    op.execute(
        "UPDATE identity_refresh_tokens "
        "SET revoked_at_utc = NOW() "
        "WHERE revoked_at_utc IS NULL AND family_id IS NULL"
    )

    # 3. Index for efficient family-based lookups during reuse detection
    op.create_index(
        "ix_identity_refresh_tokens_family",
        "identity_refresh_tokens",
        ["family_id"],
    )

    # 4. Add deactivated_at_utc to identity_users for compliance audit trail
    op.add_column(
        "identity_users",
        sa.Column("deactivated_at_utc", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("identity_users", "deactivated_at_utc")
    op.drop_index("ix_identity_refresh_tokens_family", table_name="identity_refresh_tokens")
    op.drop_column("identity_refresh_tokens", "family_id")
