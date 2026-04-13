"""faza_1_model_standard

Revision ID: i4j5k6l7m8n9
Revises: h3i4j5k6l7m8
Create Date: 2026-04-13
"""


from alembic import op

revision = "i4j5k6l7m8n9"
down_revision = "h3i4j5k6l7m8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Rename event_id -> outbox_id
    op.alter_column("trip_outbox", "event_id", new_column_name="outbox_id")

    # 2. JSONB -> Text Migration Phase 1 & 2
    op.execute("ALTER TABLE trip_outbox ADD COLUMN payload_text TEXT")
    op.execute("UPDATE trip_outbox SET payload_text = payload_json::text")
    op.execute("ALTER TABLE trip_outbox DROP COLUMN payload_json")
    op.execute("ALTER TABLE trip_outbox RENAME COLUMN payload_text TO payload_json")


def downgrade() -> None:
    # Reverse Phase 1 & 2
    op.execute("ALTER TABLE trip_outbox ADD COLUMN payload_jsonb JSONB")
    op.execute("UPDATE trip_outbox SET payload_jsonb = payload_json::jsonb")
    op.execute("ALTER TABLE trip_outbox DROP COLUMN payload_json")
    op.execute("ALTER TABLE trip_outbox RENAME COLUMN payload_jsonb TO payload_json")

    # Reverse rename
    op.alter_column("trip_outbox", "outbox_id", new_column_name="event_id")
