"""outbox_platform_standard_fields

Align fleet_outbox with PLATFORM_STANDARD.md §9:
- payload_json: JSONB → Text (portability, deterministic byte stream)
- Add partition_key (String 100)
- Add claim_token (String 50)
- Add claimed_by_worker (String 50)

Revision ID: 005_outbox_std_fields
Revises: 004_outbox_publish_state
Create Date: 2026-04-08
"""

import sqlalchemy as sa

from alembic import op

revision = "005_outbox_std_fields"
down_revision = "004_outbox_publish_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Convert payload_json from JSONB to Text (cast via ::text preserves the JSON string)
    op.execute("ALTER TABLE fleet_outbox ALTER COLUMN payload_json TYPE TEXT USING payload_json::text")

    # Add new columns for partition routing and claim ownership
    op.add_column("fleet_outbox", sa.Column("partition_key", sa.String(100), nullable=True))
    op.add_column("fleet_outbox", sa.Column("claim_token", sa.String(50), nullable=True))
    op.add_column("fleet_outbox", sa.Column("claimed_by_worker", sa.String(50), nullable=True))

    # Backfill partition_key from aggregate_id for existing rows
    op.execute("UPDATE fleet_outbox SET partition_key = aggregate_id WHERE partition_key IS NULL")


def downgrade() -> None:
    op.drop_column("fleet_outbox", "claimed_by_worker")
    op.drop_column("fleet_outbox", "claim_token")
    op.drop_column("fleet_outbox", "partition_key")

    # Convert payload_json back to JSONB
    op.execute("ALTER TABLE fleet_outbox ALTER COLUMN payload_json TYPE JSONB USING payload_json::jsonb")
