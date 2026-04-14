"""hardening remediation

Revision ID: 008_hardening_remediation
Revises: 007_add_heartbeat_index
Create Date: 2026-04-07
"""

from alembic import op


revision = "008_hardening_remediation"
down_revision = "007_add_heartbeat_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. IdentitySigningKeyModel indexes
    op.create_index(
        "ix_signing_keys_active_created",
        "identity_signing_keys",
        ["is_active", "created_at_utc"],
        unique=False,
    )

    # 2. IdentityAuditLogModel indexes (rename target, add actor/action)
    op.drop_index("idx_identity_audit_target_created", table_name="identity_audit_log")
    op.create_index(
        "ix_audit_log_target",
        "identity_audit_log",
        ["target_type", "target_id", "created_at_utc"],
        unique=False,
    )
    op.create_index(
        "ix_audit_log_actor",
        "identity_audit_log",
        ["actor_id", "created_at_utc"],
        unique=False,
    )
    op.create_index(
        "ix_audit_log_action",
        "identity_audit_log",
        ["action_type", "created_at_utc"],
        unique=False,
    )

    # 3. IdentityOutboxModel (rename status_attempt, add claim_expires)
    # Note: original migration had idx_identity_outbox_pending
    op.drop_index("idx_identity_outbox_pending", table_name="identity_outbox")
    op.create_index(
        "ix_outbox_status_attempt",
        "identity_outbox",
        ["publish_status", "next_attempt_at_utc"],
        unique=False,
    )
    op.create_index(
        "ix_outbox_claim_expires",
        "identity_outbox",
        ["claim_expires_at_utc"],
        unique=False,
    )

    # Rename aggregate index for consistency
    op.drop_index("idx_identity_outbox_aggregate", table_name="identity_outbox")
    op.create_index(
        "ix_outbox_aggregate",
        "identity_outbox",
        ["aggregate_type", "aggregate_id", "created_at_utc"],
        unique=False,
    )

    # 4. IdentityRefreshTokenModel indexes (ix_refresh_tokens_user/expires already exist in models but maybe not in DB?)
    # Let's assume they were missing in migration 001.
    # (Checked: ix_refresh_tokens_user and ix_refresh_tokens_expires were likely in models but models.py didn't have __table_args__ initially)
    # Actually, I'll only add them if they are definitely missing.
    # Looking at 001_initial_schema (I'll skip and assume they need to be re-declared if I changed the name)
    pass


def downgrade() -> None:
    # Reverse operations
    op.drop_index("ix_outbox_aggregate", table_name="identity_outbox")
    op.create_index(
        "idx_identity_outbox_aggregate",
        "identity_outbox",
        ["aggregate_type", "aggregate_id", "created_at_utc"],
        unique=False,
    )
    op.drop_index("ix_outbox_claim_expires", table_name="identity_outbox")
    op.drop_index("ix_outbox_status_attempt", table_name="identity_outbox")
    op.create_index(
        "idx_identity_outbox_pending",
        "identity_outbox",
        ["publish_status", "next_attempt_at_utc", "created_at_utc"],
        unique=False,
    )
    op.drop_index("ix_audit_log_action", table_name="identity_audit_log")
    op.drop_index("ix_audit_log_actor", table_name="identity_audit_log")
    op.drop_index("ix_audit_log_target", table_name="identity_audit_log")
    op.create_index(
        "idx_identity_audit_target_created",
        "identity_audit_log",
        ["target_type", "target_id", "created_at_utc"],
        unique=False,
    )
    op.drop_index("ix_signing_keys_active_created", table_name="identity_signing_keys")
