"""harden identity outbox schema

Revision ID: 006_harden_outbox_schema
Revises: 005_add_outbox_and_audit
Create Date: 2026-04-07
"""

from alembic import op
# sa is kept for potential future expansion but currently unused in this specific patch


revision = "006_harden_outbox_schema"
down_revision = "005_add_outbox_and_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Widen aggregate_id and change ondelete to RESTRICT
    # Note: Postgres requires dropping and recreating the constraint to change ondelete behavior efficiently in some cases,
    # or using alter_column for the type.

    op.execute("ALTER TABLE identity_outbox ALTER COLUMN aggregate_id TYPE VARCHAR(64)")

    # Drop existing FK
    op.drop_constraint(
        "identity_outbox_aggregate_id_fkey", "identity_outbox", type_="foreignkey"
    )

    # Re-add with RESTRICT
    op.create_foreign_key(
        "identity_outbox_aggregate_id_fkey",
        "identity_outbox",
        "identity_users",
        ["aggregate_id"],
        ["user_id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "identity_outbox_aggregate_id_fkey", "identity_outbox", type_="foreignkey"
    )
    op.create_foreign_key(
        "identity_outbox_aggregate_id_fkey",
        "identity_outbox",
        "identity_users",
        ["aggregate_id"],
        ["user_id"],
        ondelete="CASCADE",
    )
    op.execute("ALTER TABLE identity_outbox ALTER COLUMN aggregate_id TYPE VARCHAR(26)")
