"""SQLAlchemy models for all 9 Trip Service tables.

Implements V8 Sections 6.1–6.9 exactly.
All columns, constraints, and indexes match the specification.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all Trip Service models."""

    pass


# ---------------------------------------------------------------------------
# 6.1 trip_trips
# ---------------------------------------------------------------------------


class TripTrip(Base):
    """V8 Section 6.1 — Canonical trip record."""

    __tablename__ = "trip_trips"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)  # ULID
    trip_no: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_slip_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    base_trip_id: Mapped[str | None] = mapped_column(
        String(26),
        ForeignKey("trip_trips.id", ondelete="RESTRICT"),
        nullable=True,
    )
    driver_id: Mapped[str] = mapped_column(String(50), nullable=False)
    vehicle_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    trailer_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    route_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    trip_datetime_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trip_timezone: Mapped[str] = mapped_column(String(50), nullable=False)
    tare_weight_kg: Mapped[int] = mapped_column(Integer, nullable=False)
    gross_weight_kg: Mapped[int] = mapped_column(Integer, nullable=False)
    net_weight_kg: Mapped[int] = mapped_column(Integer, nullable=False)
    is_empty_return: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_by_actor_id: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    soft_deleted_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    soft_deleted_by_actor_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Relationships
    evidence: Mapped[list["TripTripEvidence"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan", passive_deletes=True
    )
    enrichment: Mapped["TripTripEnrichment | None"] = relationship(
        back_populates="trip", cascade="all, delete-orphan", passive_deletes=True, uselist=False
    )
    timeline: Mapped[list["TripTripTimeline"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan", passive_deletes=True
    )
    empty_return_children: Mapped[list["TripTrip"]] = relationship(
        back_populates="base_trip", foreign_keys="TripTrip.base_trip_id"
    )
    base_trip: Mapped["TripTrip | None"] = relationship(
        back_populates="empty_return_children", remote_side="TripTrip.id"
    )

    __table_args__ = (
        # V8 Section 6.1 — Check constraints
        CheckConstraint("gross_weight_kg >= 0", name="ck_trips_gross_positive"),
        CheckConstraint("tare_weight_kg >= 0", name="ck_trips_tare_positive"),
        CheckConstraint("net_weight_kg >= 0", name="ck_trips_net_positive"),
        CheckConstraint("gross_weight_kg >= tare_weight_kg", name="ck_trips_gross_gte_tare"),
        CheckConstraint("net_weight_kg = gross_weight_kg - tare_weight_kg", name="ck_trips_net_eq_diff"),
        # V8 Section 6.1 — Indexes
        Index("ix_trips_status_datetime", "status", "trip_datetime_utc", "id", postgresql_using="btree"),
        Index("ix_trips_driver_datetime", "driver_id", "trip_datetime_utc", "id", postgresql_using="btree"),
        Index("ix_trips_vehicle_datetime", "vehicle_id", "trip_datetime_utc", "id", postgresql_using="btree"),
        Index("ix_trips_route_datetime", "route_id", "trip_datetime_utc", "id", postgresql_using="btree"),
        Index("ix_trips_base_trip", "base_trip_id"),
        # V8 Section 6.1 — Partial unique index for source_slip_no
        Index(
            "uq_trips_source_slip_no_telegram",
            "source_slip_no",
            unique=True,
            postgresql_where="source_type = 'TELEGRAM_TRIP_SLIP'",
        ),
    )


# ---------------------------------------------------------------------------
# 6.2 trip_trip_evidence
# ---------------------------------------------------------------------------


class TripTripEvidence(Base):
    """V8 Section 6.2 — Non-canonical source evidence."""

    __tablename__ = "trip_trip_evidence"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    trip_id: Mapped[str] = mapped_column(String(26), ForeignKey("trip_trips.id", ondelete="CASCADE"), nullable=False)
    evidence_source: Mapped[str] = mapped_column(String(30), nullable=False)
    evidence_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    source_slip_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    telegram_message_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    file_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_text_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    normalized_truck_plate: Mapped[str | None] = mapped_column(String(50), nullable=True)
    normalized_trailer_plate: Mapped[str | None] = mapped_column(String(50), nullable=True)
    origin_name_raw: Mapped[str | None] = mapped_column(String(200), nullable=True)
    destination_name_raw: Mapped[str | None] = mapped_column(String(200), nullable=True)
    raw_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationship
    trip: Mapped["TripTrip"] = relationship(back_populates="evidence")

    __table_args__ = (
        Index("ix_evidence_trip_id", "trip_id"),
        Index("ix_evidence_source_slip", "evidence_source", "source_slip_no"),
        Index("ix_evidence_telegram_msg", "telegram_message_id"),
        Index("ix_evidence_row_number", "row_number"),
    )


# ---------------------------------------------------------------------------
# 6.3 trip_trip_enrichment
# ---------------------------------------------------------------------------


class TripTripEnrichment(Base):
    """V8 Section 6.3 — Enrichment state and worker claim state."""

    __tablename__ = "trip_trip_enrichment"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    trip_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("trip_trips.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    enrichment_status: Mapped[str] = mapped_column(String(10), nullable=False)
    route_status: Mapped[str] = mapped_column(String(10), nullable=False)
    weather_status: Mapped[str] = mapped_column(String(10), nullable=False)
    data_quality_flag: Mapped[str] = mapped_column(String(10), nullable=False)
    enrichment_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_enrichment_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    next_retry_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_token: Mapped[str | None] = mapped_column(String(50), nullable=True)
    claim_expires_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_by_worker: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationship
    trip: Mapped["TripTrip"] = relationship(back_populates="enrichment")

    __table_args__ = (
        Index("ix_enrichment_status_retry", "enrichment_status", "next_retry_at_utc"),
        Index("ix_enrichment_route", "route_status"),
        Index("ix_enrichment_weather", "weather_status"),
        Index("ix_enrichment_claim_exp", "claim_expires_at_utc"),
    )


# ---------------------------------------------------------------------------
# 6.4 trip_trip_timeline
# ---------------------------------------------------------------------------


class TripTripTimeline(Base):
    """V8 Section 6.4 — Immutable business timeline events."""

    __tablename__ = "trip_trip_timeline"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    trip_id: Mapped[str] = mapped_column(String(26), ForeignKey("trip_trips.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(50), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationship
    trip: Mapped["TripTrip"] = relationship(back_populates="timeline")

    __table_args__ = (
        Index("ix_timeline_trip_created", "trip_id", "created_at_utc"),
        Index("ix_timeline_event_created", "event_type", "created_at_utc"),
    )


# ---------------------------------------------------------------------------
# 6.5 trip_import_jobs
# ---------------------------------------------------------------------------


class TripImportJob(Base):
    """V8 Section 6.5 — Async Excel import job metadata."""

    __tablename__ = "trip_import_jobs"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    file_key: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    import_mode: Mapped[str] = mapped_column(String(10), nullable=False)
    skip_weather_enrichment: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_by_admin_id: Mapped[str] = mapped_column(String(50), nullable=False)
    imported_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enrichment_pending_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enrichment_failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    rows: Mapped[list["TripImportJobRow"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        Index("ix_import_jobs_status_created", "status", "created_at_utc"),
        Index("ix_import_jobs_admin_created", "created_by_admin_id", "created_at_utc"),
    )


# ---------------------------------------------------------------------------
# 6.6 trip_import_job_rows
# ---------------------------------------------------------------------------


class TripImportJobRow(Base):
    """V8 Section 6.6 — Per-row diagnostics for import jobs."""

    __tablename__ = "trip_import_job_rows"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("trip_import_jobs.id", ondelete="CASCADE"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    row_status: Mapped[str] = mapped_column(String(10), nullable=False)
    created_trip_id: Mapped[str | None] = mapped_column(String(26), ForeignKey("trip_trips.id"), nullable=True)
    driver_code_raw: Mapped[str | None] = mapped_column(String(50), nullable=True)
    raw_row_json: Mapped[str] = mapped_column(Text, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationship
    job: Mapped["TripImportJob"] = relationship(back_populates="rows")

    __table_args__ = (
        Index("ix_import_rows_job_number", "job_id", "row_number"),
        Index("ix_import_rows_job_status", "job_id", "row_status"),
    )


# ---------------------------------------------------------------------------
# 6.7 trip_export_jobs
# ---------------------------------------------------------------------------


class TripExportJob(Base):
    """V8 Section 6.7 — Async export job metadata."""

    __tablename__ = "trip_export_jobs"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    requested_filters_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_file_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    result_file_expires_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_admin_id: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_export_jobs_status_created", "status", "created_at_utc"),
        Index("ix_export_jobs_admin_created", "created_by_admin_id", "created_at_utc"),
    )


# ---------------------------------------------------------------------------
# 6.8 trip_outbox
# ---------------------------------------------------------------------------


class TripOutbox(Base):
    """V8 Section 6.8 — Transactional outbox for reliable event publish."""

    __tablename__ = "trip_outbox"

    event_id: Mapped[str] = mapped_column(String(26), primary_key=True)  # ULID
    aggregate_type: Mapped[str] = mapped_column(String(10), nullable=False, default="TRIP")
    aggregate_id: Mapped[str] = mapped_column(String(26), nullable=False)
    aggregate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_name: Mapped[str] = mapped_column(String(50), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    partition_key: Mapped[str] = mapped_column(String(26), nullable=False)
    publish_status: Mapped[str] = mapped_column(String(15), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index(
            "ix_outbox_status_attempt_created",
            "publish_status",
            "next_attempt_at_utc",
            "created_at_utc",
        ),
        Index("ix_outbox_aggregate", "aggregate_type", "aggregate_id", "created_at_utc"),
        Index("ix_outbox_event_name", "event_name", "created_at_utc"),
    )


# ---------------------------------------------------------------------------
# 6.9 trip_idempotency_records
# ---------------------------------------------------------------------------


class TripIdempotencyRecord(Base):
    """V8 Section 6.9 — Persisted idempotency fingerprints for admin POST endpoints."""

    __tablename__ = "trip_idempotency_records"

    idempotency_key: Mapped[str] = mapped_column(Text, primary_key=True)
    endpoint_fingerprint: Mapped[str] = mapped_column(Text, primary_key=True)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_idempotency_expires", "expires_at_utc"),)
