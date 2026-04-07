"""final forensic parity

Revision ID: 67d2b6c9a2d4
Revises: 56c1a5c9a1d3
Create Date: 2026-04-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "67d2b6c9a2d4"
down_revision = "56c1a5c9a1d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Type Conversions (Text -> JSONB)
    op.alter_column(
        "driver_audit_log", "changed_fields_json", type_=postgresql.JSONB, postgresql_using="changed_fields_json::jsonb"
    )
    op.alter_column(
        "driver_audit_log", "old_snapshot_json", type_=postgresql.JSONB, postgresql_using="old_snapshot_json::jsonb"
    )
    op.alter_column(
        "driver_audit_log", "new_snapshot_json", type_=postgresql.JSONB, postgresql_using="new_snapshot_json::jsonb"
    )
    op.alter_column("driver_outbox", "payload_json", type_=postgresql.JSONB, postgresql_using="payload_json::jsonb")
    op.alter_column(
        "driver_import_jobs", "error_summary_json", type_=postgresql.JSONB, postgresql_using="error_summary_json::jsonb"
    )
    op.alter_column(
        "driver_import_job_rows",
        "source_payload_json",
        type_=postgresql.JSONB,
        postgresql_using="source_payload_json::jsonb",
    )
    op.alter_column(
        "driver_worker_heartbeats",
        "worker_metadata_json",
        type_=postgresql.JSONB,
        postgresql_using="worker_metadata_json::jsonb",
    )

    # 2. Index Renaming
    # Driver indices
    op.drop_index("idx_driver_status", table_name="driver_drivers")
    op.create_index("ix_driver_drivers_status", "driver_drivers", ["status"])
    op.drop_index("idx_driver_phone_e164", table_name="driver_drivers")
    op.create_index("ix_driver_drivers_phone_e164", "driver_drivers", ["phone_e164"])
    op.drop_index("idx_driver_telegram_user_id", table_name="driver_drivers")
    op.create_index("ix_driver_drivers_telegram_user_id", "driver_drivers", ["telegram_user_id"])
    op.drop_index("idx_driver_company_code", table_name="driver_drivers")
    op.create_index("ix_driver_drivers_company_code", "driver_drivers", ["company_driver_code"])
    op.drop_index("idx_driver_created_at", table_name="driver_drivers")
    op.create_index("ix_driver_drivers_created_at", "driver_drivers", ["created_at_utc"])
    op.drop_index("idx_driver_updated_at", table_name="driver_drivers")
    op.create_index("ix_driver_drivers_updated_at", "driver_drivers", ["updated_at_utc"])

    # Audit indices
    op.drop_index("idx_driver_audit_driver_created", table_name="driver_audit_log")
    op.create_index("ix_driver_audit_log_driver_created", "driver_audit_log", ["driver_id", "created_at_utc"])
    op.drop_index("idx_driver_audit_actor_created", table_name="driver_audit_log")
    op.create_index("ix_driver_audit_log_actor_created", "driver_audit_log", ["actor_id", "created_at_utc"])

    # Outbox indices
    op.drop_index("idx_driver_outbox_pending", table_name="driver_outbox")
    op.create_index(
        "ix_driver_outbox_pending", "driver_outbox", ["publish_status", "next_attempt_at_utc", "created_at_utc"]
    )
    op.drop_index("idx_driver_outbox_driver_id", table_name="driver_outbox")
    op.create_index("ix_driver_outbox_driver_id", "driver_outbox", ["driver_id", "created_at_utc"])

    # Merge indices
    op.drop_index("idx_driver_merge_source", table_name="driver_merge_history")
    op.create_index("ix_driver_merge_history_source", "driver_merge_history", ["source_driver_id"])
    op.drop_index("idx_driver_merge_target", table_name="driver_merge_history")
    op.create_index("ix_driver_merge_history_target", "driver_merge_history", ["target_driver_id"])

    # Import indices
    op.drop_index("idx_driver_import_jobs_status_created", table_name="driver_import_jobs")
    op.create_index("ix_driver_import_jobs_status_created", "driver_import_jobs", ["status", "created_at_utc"])
    op.drop_index("idx_driver_import_jobs_actor_created", table_name="driver_import_jobs")
    op.create_index(
        "ix_driver_import_jobs_actor_created", "driver_import_jobs", ["created_by_actor_id", "created_at_utc"]
    )

    op.drop_index("idx_driver_import_rows_job_seq", table_name="driver_import_job_rows")
    op.create_index("ix_driver_import_job_rows_job_seq", "driver_import_job_rows", ["import_job_id", "row_no"])
    op.drop_index("idx_driver_import_rows_status", table_name="driver_import_job_rows")
    op.create_index("ix_driver_import_job_rows_status", "driver_import_job_rows", ["import_job_id", "row_status"])

    # Heartbeat index
    op.create_index("ix_driver_worker_heartbeats_last_heartbeat", "driver_worker_heartbeats", ["last_heartbeat_at_utc"])


def downgrade() -> None:
    pass
