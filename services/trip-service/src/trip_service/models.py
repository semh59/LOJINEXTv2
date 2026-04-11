"""SQLAlchemy models for Trip Service."""

from __future__ import annotations

from datetime import datetime
from typing import Any

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
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

_COMPLETE_TRIP_SQL = """
vehicle_id IS NOT NULL AND
route_pair_id IS NOT NULL AND
route_id IS NOT NULL AND
origin_location_id IS NOT NULL AND
origin_name_snapshot IS NOT NULL AND
destination_location_id IS NOT NULL AND
destination_name_snapshot IS NOT NULL AND
tare_weight_kg IS NOT NULL AND
gross_weight_kg IS NOT NULL AND
net_weight_kg IS NOT NULL AND
planned_duration_s IS NOT NULL AND
planned_end_utc IS NOT NULL
"""


class Base(DeclarativeBase):
    """Base class for all Trip Service models."""


class TripTrip(Base):
    """Canonical trip aggregate record."""

    __tablename__ = "trip_trips"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    trip_no: Mapped[str] = mapped_column(String(100), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_slip_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_reference_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    review_reason_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    base_trip_id: Mapped[str | None] = mapped_column(String(26), ForeignKey("trip_trips.id"), nullable=True)
    driver_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    vehicle_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    trailer_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    route_pair_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    route_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    origin_location_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    origin_name_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    destination_location_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    destination_name_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    trip_datetime_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trip_timezone: Mapped[str] = mapped_column(String(50), nullable=False)
    planned_duration_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    planned_end_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tare_weight_kg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gross_weight_kg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    net_weight_kg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_empty_return: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by_actor_id: Mapped[str] = mapped_column(String(26), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    soft_deleted_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    soft_deleted_by_actor_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    evidence: Mapped[list["TripTripEvidence"]] = relationship(
        back_populates="trip",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    enrichment: Mapped["TripTripEnrichment | None"] = relationship(
        back_populates="trip",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    timeline: Mapped[list["TripTripTimeline"]] = relationship(
        back_populates="trip",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    empty_return_children: Mapped[list["TripTrip"]] = relationship(
        back_populates="base_trip",
        foreign_keys="TripTrip.base_trip_id",
    )
    base_trip: Mapped["TripTrip | None"] = relationship(
        back_populates="empty_return_children",
        remote_side="TripTrip.id",
    )

    __table_args__ = (
        UniqueConstraint("trip_no", name="uq_trip_trips_trip_no"),
        CheckConstraint("planned_duration_s IS NULL OR planned_duration_s >= 0", name="ck_trips_duration_non_negative"),
        CheckConstraint("tare_weight_kg IS NULL OR tare_weight_kg >= 0", name="ck_trips_tare_positive"),
        CheckConstraint("gross_weight_kg IS NULL OR gross_weight_kg >= 0", name="ck_trips_gross_positive"),
        CheckConstraint("net_weight_kg IS NULL OR net_weight_kg >= 0", name="ck_trips_net_positive"),
        CheckConstraint(
            "gross_weight_kg IS NULL OR tare_weight_kg IS NULL OR gross_weight_kg >= tare_weight_kg",
            name="ck_trips_gross_gte_tare",
        ),
        CheckConstraint(
            """
            net_weight_kg IS NULL OR gross_weight_kg IS NULL OR tare_weight_kg IS NULL OR
            net_weight_kg = gross_weight_kg - tare_weight_kg
            """,
            name="ck_trips_net_eq_diff",
        ),
        CheckConstraint(
            f"status <> 'COMPLETED' OR ({_COMPLETE_TRIP_SQL})",
            name="ck_trips_completed_complete",
        ),
        CheckConstraint(
            f"source_type NOT IN ('ADMIN_MANUAL', 'EMPTY_RETURN_ADMIN', 'EXCEL_IMPORT') OR ({_COMPLETE_TRIP_SQL})",
            name="ck_trips_strict_sources_complete",
        ),
        CheckConstraint(
            f"review_reason_code <> 'FALLBACK_MINIMAL' OR status = 'PENDING_REVIEW' OR ({_COMPLETE_TRIP_SQL})",
            name="ck_trips_fallback_pending_only",
        ),
        CheckConstraint(
            "source_type NOT IN ('TELEGRAM_TRIP_SLIP', 'EXCEL_IMPORT') OR source_reference_key IS NOT NULL",
            name="ck_trips_imported_source_reference_key",
        ),
        Index("ix_trips_status_datetime", "status", "trip_datetime_utc", "id", postgresql_using="btree"),
        Index("ix_trips_driver_window", "driver_id", "trip_datetime_utc", "planned_end_utc", postgresql_using="btree"),
        Index(
            "ix_trips_vehicle_window",
            "vehicle_id",
            "trip_datetime_utc",
            "planned_end_utc",
            postgresql_using="btree",
        ),
        Index(
            "ix_trips_trailer_window",
            "trailer_id",
            "trip_datetime_utc",
            "planned_end_utc",
            postgresql_using="btree",
        ),
        Index("ix_trips_route_pair_datetime", "route_pair_id", "trip_datetime_utc", "id", postgresql_using="btree"),
        Index("ix_trips_base_trip", "base_trip_id"),
        Index(
            "uq_trips_empty_return_base_trip",
            "base_trip_id",
            unique=True,
            postgresql_where=text("is_empty_return = true"),
        ),
        Index(
            "ix_trip_trips_source_slip_no_telegram",
            "source_slip_no",
            unique=True,
            postgresql_where=text("source_type = 'TELEGRAM_TRIP_SLIP' AND source_slip_no IS NOT NULL"),
        ),
        Index(
            "ix_trip_trips_source_reference_key",
            "source_reference_key",
            unique=True,
            postgresql_where=text("source_reference_key IS NOT NULL"),
        ),
    )


class TripTripEvidence(Base):
    """Non-canonical source evidence."""

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
    raw_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    trip: Mapped["TripTrip"] = relationship(back_populates="evidence")

    __table_args__ = (
        Index("ix_trip_evidence_trip_id", "trip_id"),
        Index("ix_trip_evidence_source_slip", "evidence_source", "source_slip_no"),
        Index("ix_trip_evidence_telegram_msg", "telegram_message_id"),
        Index("ix_trip_evidence_row_number", "row_number"),
    )


class TripTripEnrichment(Base):
    """Enrichment state and worker claim state."""

    __tablename__ = "trip_trip_enrichment"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    trip_id: Mapped[str] = mapped_column(
        String(26),
        ForeignKey("trip_trips.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    enrichment_status: Mapped[str] = mapped_column(String(10), nullable=False)
    route_status: Mapped[str] = mapped_column(String(10), nullable=False)
    data_quality_flag: Mapped[str] = mapped_column(String(10), nullable=False)
    enrichment_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_enrichment_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    next_retry_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_token: Mapped[str | None] = mapped_column(String(50), nullable=True)
    claim_expires_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_by_worker: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    trip: Mapped["TripTrip"] = relationship(back_populates="enrichment")

    __table_args__ = (
        Index("ix_trip_enrichment_status_retry", "enrichment_status", "next_retry_at_utc"),
        Index("ix_trip_enrichment_route", "route_status"),
        Index("ix_trip_enrichment_claim_exp", "claim_expires_at_utc"),
    )


class TripTripTimeline(Base):
    """Immutable business timeline events."""

    __tablename__ = "trip_trip_timeline"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    trip_id: Mapped[str] = mapped_column(String(26), ForeignKey("trip_trips.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(26), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    trip: Mapped["TripTrip"] = relationship(back_populates="timeline")

    __table_args__ = (
        Index("ix_trip_timeline_trip_created", "trip_id", "created_at_utc"),
        Index("ix_trip_timeline_event_created", "event_type", "created_at_utc"),
    )


class TripTripDeleteAudit(Base):
    """Immutable audit record captured before a hard delete."""

    __tablename__ = "trip_trip_delete_audit"

    audit_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    trip_id: Mapped[str] = mapped_column(String(26), nullable=False)
    trip_no: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(26), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    deleted_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_trip_delete_audit_trip", "trip_id", "deleted_at_utc"),
        Index("ix_trip_delete_audit_actor", "actor_id", "deleted_at_utc"),
    )


class TripAuditLogModel(Base):
    """General high-fidelity audit log for Trip Service mutations."""

    __tablename__ = "trip_audit_log"

    audit_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    trip_id: Mapped[str] = mapped_column(String(26), nullable=False)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_fields_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    old_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    new_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    actor_id: Mapped[str] = mapped_column(String(26), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_trip_audit_log_trip_created", "trip_id", "created_at_utc"),)


class TripOutbox(Base):
    """Transactional outbox for reliable event publish."""

    __tablename__ = "trip_outbox"

    event_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    aggregate_type: Mapped[str] = mapped_column(String(10), nullable=False, default="TRIP")
    aggregate_id: Mapped[str] = mapped_column(String(26), nullable=False)
    aggregate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_name: Mapped[str] = mapped_column(String(50), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    partition_key: Mapped[str] = mapped_column(String(100), nullable=False)
    publish_status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    claim_token: Mapped[str | None] = mapped_column(String(50), nullable=True)
    claim_expires_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_by_worker: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_trip_outbox_status_attempt_created", "publish_status", "next_attempt_at_utc", "created_at_utc"),
        Index("ix_trip_outbox_aggregate", "aggregate_type", "aggregate_id", "created_at_utc"),
        Index("ix_trip_outbox_event_name", "event_name", "created_at_utc"),
        Index("ix_trip_outbox_claim_exp", "claim_expires_at_utc"),
        Index("ix_trip_outbox_partition", "partition_key", "publish_status", "created_at_utc"),
    )


class TripIdempotencyRecord(Base):
    """Persisted idempotency fingerprints for POST endpoints."""

    __tablename__ = "trip_idempotency_records"

    idempotency_key: Mapped[str] = mapped_column(Text, primary_key=True)
    endpoint_fingerprint: Mapped[str] = mapped_column(Text, primary_key=True)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_headers_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    response_body_json: Mapped[dict[str, Any] | str] = mapped_column(JSONB, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_trip_idempotency_expires", "expires_at_utc"),)


class WorkerHeartbeat(Base):
    """Persisted worker heartbeats for cross-service and multi-process readiness."""

    __tablename__ = "worker_heartbeats"

    worker_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    recorded_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
