"""initial identity schema

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-04-05
"""

from alembic import op
import sqlalchemy as sa


revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "identity_users",
        sa.Column("user_id", sa.String(length=26), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=False, unique=True),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "identity_groups",
        sa.Column("group_id", sa.String(length=26), primary_key=True),
        sa.Column("group_name", sa.String(length=64), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.create_table(
        "identity_permissions",
        sa.Column("permission_key", sa.String(length=128), primary_key=True),
        sa.Column("description", sa.Text(), nullable=True),
    )
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
    op.create_table(
        "identity_service_clients",
        sa.Column("client_id", sa.String(length=64), primary_key=True),
        sa.Column("service_name", sa.String(length=64), nullable=False, unique=True),
        sa.Column("client_secret_hash", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_at_utc", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "identity_user_groups",
        sa.Column("user_id", sa.String(length=26), sa.ForeignKey("identity_users.user_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("group_id", sa.String(length=26), sa.ForeignKey("identity_groups.group_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "identity_group_permissions",
        sa.Column("group_id", sa.String(length=26), sa.ForeignKey("identity_groups.group_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_key", sa.String(length=128), sa.ForeignKey("identity_permissions.permission_key", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "identity_refresh_tokens",
        sa.Column("token_id", sa.String(length=26), primary_key=True),
        sa.Column("user_id", sa.String(length=26), sa.ForeignKey("identity_users.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False, unique=True),
        sa.Column("expires_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_identity_refresh_user",
        "identity_refresh_tokens",
        ["user_id", "expires_at_utc"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_identity_refresh_user", table_name="identity_refresh_tokens")
    op.drop_table("identity_refresh_tokens")
    op.drop_table("identity_group_permissions")
    op.drop_table("identity_user_groups")
    op.drop_table("identity_service_clients")
    op.drop_table("identity_signing_keys")
    op.drop_table("identity_permissions")
    op.drop_table("identity_groups")
    op.drop_table("identity_users")
