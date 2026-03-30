"""SQLAlchemy ORM models for Driver Service (spec Sections 2.1–2.6).

Tables:
  - driver_drivers        — canonical driver records
  - driver_audit_log      — immutable audit history
  - driver_outbox         — transactional outbox for reliable events
  - driver_merge_history  — duplicate consolidation history
  - driver_import_jobs    — async import job metadata
  - driver_import_job_rows — per-row import detail
"""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all Driver Service models."""

    pass


# ---------------------------------------------------------------------------
# 2.1  driver_drivers — canonical driver records
# ---------------------------------------------------------------------------


class DriverModel(Base):
    """Canonical driver master data record."""

    __tablename__ = "driver_drivers"

    # PK
    driver_id: Mapped[str] = mapped_column(String(26), primary_key=True)

    # Identity fields
    company_driver_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name_search_key: Mapped[str] = mapped_column(String(255), nullable=False)

    # Phone
    phone_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phone_e164: Mapped[str | None] = mapped_column(String(32), nullable=True)
    phone_normalization_status: Mapped[str] = mapped_column(String(32), nullable=False, default="MISSING")

    # Telegram
    telegram_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Employment
    license_class: Mapped[str] = mapped_column(String(32), nullable=False)
    employment_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    employment_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Status and lifecycle
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    inactive_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Generated stored column — DB-level computation
    is_assignable: Mapped[bool] = mapped_column(
        Boolean,
        Computed("status = 'ACTIVE' AND soft_deleted_at_utc IS NULL", persisted=True),
        nullable=False,
    )

    # Admin note
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optimistic locking
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Audit timestamps
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by_actor_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # Soft delete
    soft_deleted_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    soft_deleted_by_actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    soft_delete_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        # Check constraints
        CheckConstraint("full_name <> ''", name="ck_driver_full_name_not_empty"),
        CheckConstraint("full_name_search_key <> ''", name="ck_driver_search_key_not_empty"),
        CheckConstraint("license_class <> ''", name="ck_driver_license_class_not_empty"),
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_driver_status_valid"),
        CheckConstraint(
            "employment_end_date IS NULL OR employment_end_date >= employment_start_date",
            name="ck_driver_end_after_start",
        ),
        CheckConstraint(
            "phone_normalization_status IN ('NORMALIZED', 'RAW_UNKNOWN', 'INVALID', 'MISSING')",
            name="ck_driver_phone_norm_status_valid",
        ),
        # Partial unique constraints (live rows only)
        Index(
            "uq_driver_company_code_live",
            "company_driver_code",
            unique=True,
            postgresql_where=text("company_driver_code IS NOT NULL AND soft_deleted_at_utc IS NULL"),
        ),
        Index(
            "uq_driver_phone_e164_live",
            "phone_e164",
            unique=True,
            postgresql_where=text("phone_e164 IS NOT NULL AND soft_deleted_at_utc IS NULL"),
        ),
        Index(
            "uq_driver_telegram_user_id_live",
            "telegram_user_id",
            unique=True,
            postgresql_where=text("telegram_user_id IS NOT NULL AND soft_deleted_at_utc IS NULL"),
        ),
        # Performance indexes
        Index("idx_driver_status", "status", "soft_deleted_at_utc"),
        Index("idx_driver_phone_e164", "phone_e164"),
        Index("idx_driver_telegram_user_id", "telegram_user_id"),
        Index("idx_driver_company_code", "company_driver_code"),
        Index("idx_driver_created_at", "created_at_utc"),
        Index("idx_driver_updated_at", "updated_at_utc"),
    )


# ---------------------------------------------------------------------------
# 2.2  driver_audit_log — immutable audit history
# ---------------------------------------------------------------------------


class DriverAuditLogModel(Base):
    """Immutable audit record for driver identity and lifecycle mutations."""

    __tablename__ = "driver_audit_log"

    audit_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    driver_id: Mapped[str] = mapped_column(String(26), nullable=False, index=False)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_fields_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    old_snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "action_type IN ('CREATE','UPDATE','STATUS_CHANGE','SOFT_DELETE','RESTORE',"
            "'HARD_DELETE','MERGE','IMPORT_CREATE','IMPORT_UPDATE')",
            name="ck_driver_audit_action_type_valid",
        ),
        Index("idx_driver_audit_driver_created", "driver_id", "created_at_utc"),
        Index("idx_driver_audit_actor_created", "actor_id", "created_at_utc"),
    )


# ---------------------------------------------------------------------------
# 2.3  driver_outbox — transactional outbox for reliable event publishing
# ---------------------------------------------------------------------------


class DriverOutboxModel(Base):
    """Transactional outbox row for reliable driver event publishing."""

    __tablename__ = "driver_outbox"

    outbox_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    driver_id: Mapped[str] = mapped_column(String(26), nullable=False)
    event_name: Mapped[str] = mapped_column(String(128), nullable=False)
    event_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    publish_status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "publish_status IN ('PENDING', 'PUBLISHED', 'FAILED', 'DEAD_LETTER')",
            name="ck_driver_outbox_status_valid",
        ),
        Index("idx_driver_outbox_pending", "publish_status", "next_attempt_at_utc", "created_at_utc"),
        Index("idx_driver_outbox_driver_id", "driver_id", "created_at_utc"),
    )


# ---------------------------------------------------------------------------
# 2.4  driver_merge_history — duplicate consolidation history
# ---------------------------------------------------------------------------


class DriverMergeHistoryModel(Base):
    """Record of a duplicate-driver merge operation."""

    __tablename__ = "driver_merge_history"

    merge_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    source_driver_id: Mapped[str] = mapped_column(String(26), nullable=False)
    target_driver_id: Mapped[str] = mapped_column(String(26), nullable=False)
    merge_reason: Mapped[str] = mapped_column(String(255), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    merged_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "source_driver_id <> target_driver_id",
            name="ck_driver_merge_different_ids",
        ),
        Index("idx_driver_merge_source", "source_driver_id"),
        Index("idx_driver_merge_target", "target_driver_id"),
    )


# ---------------------------------------------------------------------------
# 2.5  driver_import_jobs — async import job metadata
# ---------------------------------------------------------------------------


class DriverImportJobModel(Base):
    """Async import job metadata for legacy/historical driver loads."""

    __tablename__ = "driver_import_jobs"

    import_job_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload_format: Mapped[str | None] = mapped_column(String(32), nullable=True, default="JSON")
    strict_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'PARTIAL_SUCCESS', 'CANCELLED')",
            name="ck_driver_import_job_status_valid",
        ),
        Index("idx_driver_import_jobs_status_created", "status", "created_at_utc"),
        Index("idx_driver_import_jobs_actor_created", "created_by_actor_id", "created_at_utc"),
    )


# ---------------------------------------------------------------------------
# 2.6  driver_import_job_rows — per-row import detail
# ---------------------------------------------------------------------------


class DriverImportJobRowModel(Base):
    """Per-row validation and result details for an import job."""

    __tablename__ = "driver_import_job_rows"

    import_row_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    import_job_id: Mapped[str] = mapped_column(String(26), nullable=False)
    row_no: Mapped[int] = mapped_column(Integer, nullable=False)
    source_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    resolved_driver_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "row_status IN ('PENDING', 'CREATED', 'UPDATED', 'SKIPPED', 'FAILED')",
            name="ck_driver_import_row_status_valid",
        ),
        Index("idx_driver_import_rows_job_seq", "import_job_id", "row_no"),
        Index("idx_driver_import_rows_status", "import_job_id", "row_status"),
    )
