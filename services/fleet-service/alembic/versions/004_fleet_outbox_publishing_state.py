"""fleet_outbox_publishing_state

Revision ID: 004_fleet_outbox_publishing_state
Revises: 003_final_forensic_parity
Create Date: 2026-04-07
"""

import sqlalchemy as sa

from alembic import op

revision = "004_outbox_publish_state"
down_revision = "003_final_forensic_parity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fleet_outbox",
        sa.Column("claim_expires_at_utc", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("ALTER TABLE fleet_outbox DROP CONSTRAINT fleet_outbox_publish_status_check;")
    op.execute(
        "ALTER TABLE fleet_outbox ADD CONSTRAINT fleet_outbox_publish_status_check "
        "CHECK (publish_status IN ('PENDING','PUBLISHED','FAILED','DEAD_LETTER','PUBLISHING'));"
    )
    op.execute("DROP INDEX ix_fleet_outbox_worker_poll;")
    op.execute(
        "CREATE INDEX ix_fleet_outbox_worker_poll "
        "ON fleet_outbox (publish_status, next_attempt_at_utc, created_at_utc) "
        "WHERE publish_status IN ('PENDING', 'FAILED', 'PUBLISHING');"
    )
    op.execute("DROP INDEX ix_fleet_outbox_aggregate_status;")
    op.execute(
        "CREATE INDEX ix_fleet_outbox_aggregate_status "
        "ON fleet_outbox (aggregate_id, publish_status) "
        "WHERE publish_status IN ('PENDING', 'FAILED', 'PUBLISHING');"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_fleet_outbox_aggregate_status;")
    op.execute(
        "CREATE INDEX ix_fleet_outbox_aggregate_status "
        "ON fleet_outbox (aggregate_id, publish_status) "
        "WHERE publish_status IN ('PENDING', 'FAILED');"
    )
    op.execute("DROP INDEX ix_fleet_outbox_worker_poll;")
    op.execute(
        "CREATE INDEX ix_fleet_outbox_worker_poll "
        "ON fleet_outbox (publish_status, next_attempt_at_utc, created_at_utc) "
        "WHERE publish_status IN ('PENDING', 'FAILED');"
    )
    op.execute("ALTER TABLE fleet_outbox DROP CONSTRAINT fleet_outbox_publish_status_check;")
    op.execute(
        "ALTER TABLE fleet_outbox ADD CONSTRAINT fleet_outbox_publish_status_check "
        "CHECK (publish_status IN ('PENDING','PUBLISHED','FAILED','DEAD_LETTER'));"
    )
    op.drop_column("fleet_outbox", "claim_expires_at_utc")
