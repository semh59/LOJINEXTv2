"""hardening remediation

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-04-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a2b3c4d5e6f7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass

    # 2. LocationOutboxModel additional columns and indexes
    op.add_column(
        "location_outbox", sa.Column("partition_key", sa.String(length=64), nullable=False, server_default="DEFAULT")
    )
    op.add_column("location_outbox", sa.Column("last_error_code", sa.String(length=100), nullable=True))
    op.add_column("location_outbox", sa.Column("claim_expires_at_utc", sa.DateTime(timezone=True), nullable=True))

    op.create_index(
        "idx_location_outbox_partition",
        "location_outbox",
        ["partition_key"],
        unique=False,
    )
    op.create_index(
        "idx_location_outbox_claim",
        "location_outbox",
        ["claim_expires_at_utc"],
        unique=False,
        postgresql_where=sa.text("publish_status = 'PUBLISHING'"),
    )

    # 3. LocationAuditLogModel additional column and indexes
    op.add_column("location_audit_log", sa.Column("reason", sa.Text(), nullable=True))

    op.create_index(
        "idx_location_audit_actor",
        "location_audit_log",
        ["actor_id", "created_at_utc"],
        unique=False,
    )
    op.create_index(
        "idx_location_audit_action",
        "location_audit_log",
        ["action_type", "created_at_utc"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_location_audit_action", table_name="location_audit_log")
    op.drop_index("idx_location_audit_actor", table_name="location_audit_log")
    op.drop_column("location_audit_log", "reason")
    op.drop_index("idx_location_outbox_claim", table_name="location_outbox")
    op.drop_index("idx_location_outbox_partition", table_name="location_outbox")
    op.drop_column("location_outbox", "claim_expires_at_utc")
    op.drop_column("location_outbox", "last_error_code")
    op.drop_column("location_outbox", "partition_key")
    op.drop_index("idx_processing_run_trip", table_name="processing_runs")
