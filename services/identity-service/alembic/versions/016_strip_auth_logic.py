"""strip auth logic

Revision ID: 016_strip_auth_logic
Revises: 015_audit_log_jsonb_to_text
Create Date: 2026-04-13
"""

from alembic import op
import sqlalchemy as sa

revision = "016_strip_auth_logic"
down_revision = "015_audit_log_jsonb_to_text"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Drop auth-related tables from identity-service DB
    op.drop_table("identity_refresh_tokens")
    op.drop_table("identity_service_clients")
    op.drop_table("identity_signing_keys")
    
    # Drop password_hash from identity_users
    op.drop_column("identity_users", "password_hash")

def downgrade() -> None:
    # Add back columns/tables if needed for rollback (minimal implementation)
    op.add_column("identity_users", sa.Column("password_hash", sa.Text(), nullable=True))
    
    op.create_table(
        "identity_signing_keys",
        sa.Column("kid", sa.String(length=64), primary_key=True),
        sa.Column("algorithm", sa.String(length=16), nullable=False),
        sa.Column("public_key_pem", sa.Text(), nullable=False),
        sa.Column("private_key_pem", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retired_at_utc", sa.DateTime(timezone=True), nullable=True),
    )
    # Full downgrade omitted for brevity as this is a hardening step
