"""001 — Initial Driver Service schema (spec Sections 2.1–2.6).

Creates 6 tables:
  - driver_drivers (canonical driver records with generated is_assignable column)
  - driver_audit_log (immutable audit history)
  - driver_outbox (transactional outbox)
  - driver_merge_history (duplicate consolidation)
  - driver_import_jobs (async import metadata)
  - driver_import_job_rows (per-row import detail)

Revision ID: 001
Revises: None
Create Date: 2026-03-29
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pg_trgm extension for fuzzy search
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # -----------------------------------------------------------------------
    # 2.1  driver_drivers
    # -----------------------------------------------------------------------
    op.create_table(
        "driver_drivers",
        sa.Column("driver_id", sa.String(26), primary_key=True),
        sa.Column("company_driver_code", sa.String(64), nullable=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("full_name_search_key", sa.String(255), nullable=False),
        sa.Column("phone_raw", sa.String(64), nullable=True),
        sa.Column("phone_e164", sa.String(32), nullable=True),
        sa.Column("phone_normalization_status", sa.String(32), nullable=False, server_default="MISSING"),
        sa.Column("telegram_user_id", sa.String(64), nullable=True),
        sa.Column("license_class", sa.String(32), nullable=False),
        sa.Column("employment_start_date", sa.Date, nullable=False),
        sa.Column("employment_end_date", sa.Date, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("inactive_reason", sa.String(255), nullable=True),
        sa.Column(
            "is_assignable",
            sa.Boolean,
            sa.Computed("status = 'ACTIVE' AND soft_deleted_at_utc IS NULL", persisted=True),
            nullable=False,
        ),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("row_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by_actor_id", sa.String(64), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_by_actor_id", sa.String(64), nullable=False),
        sa.Column("soft_deleted_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("soft_deleted_by_actor_id", sa.String(64), nullable=True),
        sa.Column("soft_delete_reason", sa.String(255), nullable=True),
        # Check constraints
        sa.CheckConstraint("full_name <> ''", name="ck_driver_full_name_not_empty"),
        sa.CheckConstraint("full_name_search_key <> ''", name="ck_driver_search_key_not_empty"),
        sa.CheckConstraint("license_class <> ''", name="ck_driver_license_class_not_empty"),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_driver_status_valid"),
        sa.CheckConstraint(
            "employment_end_date IS NULL OR employment_end_date >= employment_start_date",
            name="ck_driver_end_after_start",
        ),
        sa.CheckConstraint(
            "phone_normalization_status IN ('NORMALIZED', 'RAW_UNKNOWN', 'INVALID', 'MISSING')",
            name="ck_driver_phone_norm_status_valid",
        ),
    )

    # Partial unique indexes (live rows only — soft_deleted_at_utc IS NULL)
    op.execute(
        "CREATE UNIQUE INDEX uq_driver_company_code_live "
        "ON driver_drivers (company_driver_code) "
        "WHERE company_driver_code IS NOT NULL AND soft_deleted_at_utc IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_driver_phone_e164_live "
        "ON driver_drivers (phone_e164) "
        "WHERE phone_e164 IS NOT NULL AND soft_deleted_at_utc IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_driver_telegram_user_id_live "
        "ON driver_drivers (telegram_user_id) "
        "WHERE telegram_user_id IS NOT NULL AND soft_deleted_at_utc IS NULL"
    )

    # GIN trigram index for fuzzy search
    op.execute(
        "CREATE INDEX idx_driver_full_name_search_trgm ON driver_drivers USING gin (full_name_search_key gin_trgm_ops)"
    )

    # Performance indexes
    op.create_index("idx_driver_status", "driver_drivers", ["status", "soft_deleted_at_utc"])
    op.create_index("idx_driver_phone_e164", "driver_drivers", ["phone_e164"])
    op.create_index("idx_driver_telegram_user_id", "driver_drivers", ["telegram_user_id"])
    op.create_index("idx_driver_company_code", "driver_drivers", ["company_driver_code"])
    op.create_index("idx_driver_created_at", "driver_drivers", ["created_at_utc"], postgresql_using="btree")
    op.create_index("idx_driver_updated_at", "driver_drivers", ["updated_at_utc"], postgresql_using="btree")

    # -----------------------------------------------------------------------
    # 2.2  driver_audit_log
    # -----------------------------------------------------------------------
    op.create_table(
        "driver_audit_log",
        sa.Column("audit_id", sa.String(26), primary_key=True),
        sa.Column("driver_id", sa.String(26), nullable=False),
        sa.Column("action_type", sa.String(32), nullable=False),
        sa.Column("changed_fields_json", sa.Text, nullable=True),
        sa.Column("old_snapshot_json", sa.Text, nullable=True),
        sa.Column("new_snapshot_json", sa.Text, nullable=True),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("actor_role", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "action_type IN ('CREATE','UPDATE','STATUS_CHANGE','SOFT_DELETE','RESTORE',"
            "'HARD_DELETE','MERGE','IMPORT_CREATE','IMPORT_UPDATE')",
            name="ck_driver_audit_action_type_valid",
        ),
    )
    op.create_index("idx_driver_audit_driver_created", "driver_audit_log", ["driver_id", "created_at_utc"])
    op.create_index("idx_driver_audit_actor_created", "driver_audit_log", ["actor_id", "created_at_utc"])

    # -----------------------------------------------------------------------
    # 2.3  driver_outbox
    # -----------------------------------------------------------------------
    op.create_table(
        "driver_outbox",
        sa.Column("outbox_id", sa.String(26), primary_key=True),
        sa.Column("driver_id", sa.String(26), nullable=False),
        sa.Column("event_name", sa.String(128), nullable=False),
        sa.Column("event_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("payload_json", sa.Text, nullable=False),
        sa.Column("publish_status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("published_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "publish_status IN ('PENDING', 'PUBLISHED', 'FAILED', 'DEAD_LETTER')",
            name="ck_driver_outbox_status_valid",
        ),
    )
    op.create_index(
        "idx_driver_outbox_pending", "driver_outbox", ["publish_status", "next_attempt_at_utc", "created_at_utc"]
    )
    op.create_index("idx_driver_outbox_driver_id", "driver_outbox", ["driver_id", "created_at_utc"])

    # -----------------------------------------------------------------------
    # 2.4  driver_merge_history
    # -----------------------------------------------------------------------
    op.create_table(
        "driver_merge_history",
        sa.Column("merge_id", sa.String(26), primary_key=True),
        sa.Column("source_driver_id", sa.String(26), nullable=False),
        sa.Column("target_driver_id", sa.String(26), nullable=False),
        sa.Column("merge_reason", sa.String(255), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("actor_role", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("merged_at_utc", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("source_driver_id <> target_driver_id", name="ck_driver_merge_different_ids"),
    )
    op.create_index("idx_driver_merge_source", "driver_merge_history", ["source_driver_id"])
    op.create_index("idx_driver_merge_target", "driver_merge_history", ["target_driver_id"])

    # -----------------------------------------------------------------------
    # 2.5  driver_import_jobs
    # -----------------------------------------------------------------------
    op.create_table(
        "driver_import_jobs",
        sa.Column("import_job_id", sa.String(26), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("total_rows", sa.Integer, nullable=False, server_default="0"),
        sa.Column("success_rows", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed_rows", sa.Integer, nullable=False, server_default="0"),
        sa.Column("payload_format", sa.String(32), nullable=True, server_default="JSON"),
        sa.Column("strict_mode", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_by_actor_id", sa.String(64), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_summary_json", sa.Text, nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'PARTIAL_SUCCESS', 'CANCELLED')",
            name="ck_driver_import_job_status_valid",
        ),
    )
    op.create_index("idx_driver_import_jobs_status_created", "driver_import_jobs", ["status", "created_at_utc"])
    op.create_index(
        "idx_driver_import_jobs_actor_created", "driver_import_jobs", ["created_by_actor_id", "created_at_utc"]
    )

    # -----------------------------------------------------------------------
    # 2.6  driver_import_job_rows
    # -----------------------------------------------------------------------
    op.create_table(
        "driver_import_job_rows",
        sa.Column("import_row_id", sa.String(26), primary_key=True),
        sa.Column("import_job_id", sa.String(26), nullable=False),
        sa.Column("row_no", sa.Integer, nullable=False),
        sa.Column("source_payload_json", sa.Text, nullable=True),
        sa.Column("row_status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("resolved_driver_id", sa.String(26), nullable=True),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "row_status IN ('PENDING', 'CREATED', 'UPDATED', 'SKIPPED', 'FAILED')",
            name="ck_driver_import_row_status_valid",
        ),
    )
    op.create_index("idx_driver_import_rows_job_seq", "driver_import_job_rows", ["import_job_id", "row_no"])
    op.create_index("idx_driver_import_rows_status", "driver_import_job_rows", ["import_job_id", "row_status"])


def downgrade() -> None:
    op.drop_table("driver_import_job_rows")
    op.drop_table("driver_import_jobs")
    op.drop_table("driver_merge_history")
    op.drop_table("driver_outbox")
    op.drop_table("driver_audit_log")
    op.drop_table("driver_drivers")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
