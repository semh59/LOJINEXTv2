"""final forensic parity

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-04-07
"""

from alembic import op
import sqlalchemy as sa

revision = "b3c4d5e6f7a8"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. RoutePair Index Renaming
    op.drop_index("idx_route_pairs_live_unique", table_name="route_pairs")
    op.create_index(
        "ix_location_route_pairs_live_unique",
        "route_pairs",
        ["origin_location_id", "destination_location_id", "profile_code"],
        unique=True,
        postgresql_where=sa.text("pair_status IN ('ACTIVE', 'DRAFT')"),
    )

    # 2. RouteVersion Index Renaming
    op.drop_index("idx_route_versions_active_unique", table_name="route_versions")
    op.create_index(
        "ix_location_route_versions_active_unique",
        "route_versions",
        ["route_id"],
        unique=True,
        postgresql_where=sa.text("processing_status = 'ACTIVE'"),
    )

    # 3. ProcessingRun Index Renaming (idx never existed, so we just create the correct one)
    op.create_index("ix_location_processing_runs_route_pair", "processing_runs", ["route_pair_id"])

    op.drop_index("idx_processing_runs_queued_running_unique", table_name="processing_runs")
    op.create_index(
        "ix_location_processing_runs_queued_running_unique",
        "processing_runs",
        ["route_pair_id"],
        unique=True,
        postgresql_where=sa.text("run_status IN ('QUEUED', 'RUNNING')"),
    )

    # 4. Outbox Index Renaming (from idx_ to ix_)
    op.drop_index("idx_location_outbox_pending", table_name="location_outbox")
    op.create_index(
        "ix_location_outbox_pending", "location_outbox", ["publish_status", "next_attempt_at_utc", "created_at_utc"]
    )

    op.drop_index("idx_location_outbox_partition", table_name="location_outbox")
    op.create_index("ix_location_outbox_partition", "location_outbox", ["partition_key"])

    op.drop_index("idx_location_outbox_claim", table_name="location_outbox")
    op.create_index(
        "ix_location_outbox_claim",
        "location_outbox",
        ["claim_expires_at_utc"],
        postgresql_where=sa.text("publish_status = 'PUBLISHING'"),
    )

    # 5. Audit Log Index Renaming
    op.drop_index("idx_location_audit_target", table_name="location_audit_log")
    op.create_index("ix_location_audit_target", "location_audit_log", ["target_type", "target_id", "created_at_utc"])

    op.drop_index("idx_location_audit_actor", table_name="location_audit_log")
    op.create_index("ix_location_audit_actor", "location_audit_log", ["actor_id", "created_at_utc"])

    op.drop_index("idx_location_audit_action", table_name="location_audit_log")
    op.create_index("ix_location_audit_action", "location_audit_log", ["action_type", "created_at_utc"])


def downgrade() -> None:
    pass
