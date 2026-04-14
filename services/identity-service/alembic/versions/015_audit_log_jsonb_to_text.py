"""audit_log_jsonb_to_text

Revision ID: 015_audit_log_jsonb_to_text
Revises: 014_faza_1_identity
Create Date: 2026-04-13
"""

from alembic import op

revision = "015_audit_log_jsonb_to_text"
down_revision = "014_faza_1_identity"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Safely cast identity_audit_log JSONB columns to TEXT to match models.py
    
    # old_snapshot_json
    op.execute("ALTER TABLE identity_audit_log ADD COLUMN old_snapshot_text TEXT")
    op.execute("UPDATE identity_audit_log SET old_snapshot_text = old_snapshot_json::text")
    op.execute("ALTER TABLE identity_audit_log DROP COLUMN old_snapshot_json")
    op.execute("ALTER TABLE identity_audit_log RENAME COLUMN old_snapshot_text TO old_snapshot_json")

    # new_snapshot_json
    op.execute("ALTER TABLE identity_audit_log ADD COLUMN new_snapshot_text TEXT")
    op.execute("UPDATE identity_audit_log SET new_snapshot_text = new_snapshot_json::text")
    op.execute("ALTER TABLE identity_audit_log DROP COLUMN new_snapshot_json")
    op.execute("ALTER TABLE identity_audit_log RENAME COLUMN new_snapshot_text TO new_snapshot_json")

def downgrade() -> None:
    pass
