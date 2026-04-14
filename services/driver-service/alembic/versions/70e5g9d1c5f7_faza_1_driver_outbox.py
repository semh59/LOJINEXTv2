"""faza_1_driver_outbox

Revision ID: 70e5g9d1c5f7
Revises: 69d4f8c0b4e6
Create Date: 2026-04-13
"""


from alembic import op

revision = "70e5g9d1c5f7"
down_revision = "69d4f8c0b4e6"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1. Rename event_id -> outbox_id
    op.alter_column('driver_outbox', 'event_id', new_column_name='outbox_id')

    # 2. JSONB -> Text Migration Phase 1 & 2
    op.execute("ALTER TABLE driver_outbox ADD COLUMN payload_text TEXT")
    op.execute("UPDATE driver_outbox SET payload_text = payload_json::text")
    op.execute("ALTER TABLE driver_outbox DROP COLUMN payload_json")
    op.execute("ALTER TABLE driver_outbox RENAME COLUMN payload_text TO payload_json")

def downgrade() -> None:
    # Reverse Phase 1 & 2
    op.execute("ALTER TABLE driver_outbox ADD COLUMN payload_jsonb JSONB")
    op.execute("UPDATE driver_outbox SET payload_jsonb = payload_json::jsonb")
    op.execute("ALTER TABLE driver_outbox DROP COLUMN payload_json")
    op.execute("ALTER TABLE driver_outbox RENAME COLUMN payload_jsonb TO payload_json")

    # Reverse rename
    op.alter_column('driver_outbox', 'outbox_id', new_column_name='event_id')
