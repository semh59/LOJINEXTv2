"""faza_1_identity_outbox

Revision ID: 014_faza_1_identity
Revises: 013_outbox_trace_indexes
Create Date: 2026-04-13
"""

from alembic import op

revision = "014_faza_1_identity"
down_revision = "013_outbox_trace_indexes"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 2-phase JSONB -> Text strategy (even if currently TEXT, applying safe strategy)
    op.execute("ALTER TABLE identity_outbox ADD COLUMN payload_text TEXT")
    op.execute("UPDATE identity_outbox SET payload_text = payload_json::text")
    op.execute("ALTER TABLE identity_outbox DROP COLUMN payload_json")
    op.execute("ALTER TABLE identity_outbox RENAME COLUMN payload_text TO payload_json")

def downgrade() -> None:
    pass
