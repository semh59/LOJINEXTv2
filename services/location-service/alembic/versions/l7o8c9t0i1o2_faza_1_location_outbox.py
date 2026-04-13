"""faza_1_location_outbox

Revision ID: l7o8c9t0i1o2
Revises: l1o2c3t4i5o6
Create Date: 2026-04-13
"""

from alembic import op

revision = "l7o8c9t0i1o2"
down_revision = "l1o2c3t4i5o6"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 2-phase JSONB -> Text strategy (even if currently TEXT, applying safe strategy)
    op.execute("ALTER TABLE location_outbox ADD COLUMN payload_text TEXT")
    op.execute("UPDATE location_outbox SET payload_text = payload_json::text")
    op.execute("ALTER TABLE location_outbox DROP COLUMN payload_json")
    op.execute("ALTER TABLE location_outbox RENAME COLUMN payload_text TO payload_json")

def downgrade() -> None:
    pass
