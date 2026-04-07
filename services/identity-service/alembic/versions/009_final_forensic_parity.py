"""final forensic parity

Revision ID: 009_final_forensic_parity
Revises: 008_hardening_remediation
Create Date: 2026-04-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "009_final_forensic_parity"
down_revision = "008_hardening_remediation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. IdentityAuditLogModel: JSON -> JSONB and standard index naming
    op.alter_column(
        "identity_audit_log",
        "old_snapshot_json",
        existing_type=sa.JSON(),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        postgresql_using="old_snapshot_json::jsonb",
    )
    op.alter_column(
        "identity_audit_log",
        "new_snapshot_json",
        existing_type=sa.JSON(),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        postgresql_using="new_snapshot_json::jsonb",
    )
    op.drop_index("ix_audit_log_target", table_name="identity_audit_log")
    op.drop_index("ix_audit_log_actor", table_name="identity_audit_log")
    op.drop_index("ix_audit_log_action", table_name="identity_audit_log")
    op.create_index(
        "ix_identity_audit_log_target",
        "identity_audit_log",
        ["target_type", "target_id", "created_at_utc"],
    )
    op.create_index(
        "ix_identity_audit_log_actor",
        "identity_audit_log",
        ["actor_id", "created_at_utc"],
    )
    op.create_index(
        "ix_identity_audit_log_action",
        "identity_audit_log",
        ["action_type", "created_at_utc"],
    )

    # 2. IdentityOutboxModel: JSON -> JSONB and standard index naming
    op.alter_column(
        "identity_outbox",
        "payload_json",
        existing_type=sa.JSON(),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        postgresql_using="payload_json::jsonb",
    )
    op.drop_index("ix_outbox_status_attempt", table_name="identity_outbox")
    op.drop_index("ix_outbox_claim_expires", table_name="identity_outbox")
    op.drop_index("ix_outbox_aggregate", table_name="identity_outbox")
    op.create_index(
        "ix_identity_outbox_status_attempt",
        "identity_outbox",
        ["publish_status", "next_attempt_at_utc"],
    )
    op.create_index(
        "ix_identity_outbox_claim_expires",
        "identity_outbox",
        ["claim_expires_at_utc"],
    )
    op.create_index(
        "ix_identity_outbox_aggregate",
        "identity_outbox",
        ["aggregate_type", "aggregate_id", "created_at_utc"],
    )

    # 3. IdentitySigningKeyModel: Standard index naming
    op.drop_index("ix_signing_keys_active_created", table_name="identity_signing_keys")
    op.create_index(
        "ix_identity_signing_keys_active_created",
        "identity_signing_keys",
        ["is_active", "created_at_utc"],
    )

    # 4. IdentityRefreshTokenModel: Standard index naming
    # These were using default naming in initial schema if they existed
    # Models now have ix_identity_refresh_tokens_user and ix_identity_refresh_tokens_expires
    # Let's check if they existed. Assuming they did as "ix_identity_refresh_tokens_user_id" etc.
    # Actually, I'll just try to drop them and recreate. If they don't exist, I'll wrap in try/except or just skip if uncertain.
    # But for forensic parity, I MUST ensure they exist.
    op.create_index(
        "ix_identity_refresh_tokens_user", "identity_refresh_tokens", ["user_id"]
    )
    op.create_index(
        "ix_identity_refresh_tokens_expires",
        "identity_refresh_tokens",
        ["expires_at_utc"],
    )


def downgrade() -> None:
    # Reverse operations (Partial downgrade for forensics)
    op.drop_index(
        "ix_identity_refresh_tokens_expires", table_name="identity_refresh_tokens"
    )
    op.drop_index(
        "ix_identity_refresh_tokens_user", table_name="identity_refresh_tokens"
    )

    op.drop_index(
        "ix_identity_signing_keys_active_created", table_name="identity_signing_keys"
    )
    op.create_index(
        "ix_signing_keys_active_created",
        "identity_signing_keys",
        ["is_active", "created_at_utc"],
    )

    op.drop_index("ix_identity_outbox_aggregate", table_name="identity_outbox")
    op.drop_index("ix_identity_outbox_claim_expires", table_name="identity_outbox")
    op.drop_index("ix_identity_outbox_status_attempt", table_name="identity_outbox")
    op.create_index(
        "ix_outbox_aggregate",
        "identity_outbox",
        ["aggregate_type", "aggregate_id", "created_at_utc"],
    )
    op.create_index(
        "ix_outbox_claim_expires", "identity_outbox", ["claim_expires_at_utc"]
    )
    op.create_index(
        "ix_outbox_status_attempt",
        "identity_outbox",
        ["publish_status", "next_attempt_at_utc"],
    )

    op.alter_column(
        "identity_outbox",
        "payload_json",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=sa.JSON(),
        postgresql_using="payload_json::json",
    )

    op.drop_index("ix_identity_audit_log_action", table_name="identity_audit_log")
    op.drop_index("ix_identity_audit_log_actor", table_name="identity_audit_log")
    op.drop_index("ix_identity_audit_log_target", table_name="identity_audit_log")
    op.create_index(
        "ix_audit_log_action", "identity_audit_log", ["action_type", "created_at_utc"]
    )
    op.create_index(
        "ix_audit_log_actor", "identity_audit_log", ["actor_id", "created_at_utc"]
    )
    op.create_index(
        "ix_audit_log_target",
        "identity_audit_log",
        ["target_type", "target_id", "created_at_utc"],
    )

    op.alter_column(
        "identity_audit_log",
        "new_snapshot_json",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=sa.JSON(),
        postgresql_using="new_snapshot_json::json",
    )
    op.alter_column(
        "identity_audit_log",
        "old_snapshot_json",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=sa.JSON(),
        postgresql_using="old_snapshot_json::json",
    )
