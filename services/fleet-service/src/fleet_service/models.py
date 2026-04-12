"""SQLAlchemy ORM models for Fleet Service (Section 8).

All models use raw SQL table definitions from the Alembic migration.
Models are defined declaratively using mapped_column for type safety.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB  # noqa: F401 — used by timeline/audit models
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all Fleet Service ORM models."""


# === 8.2 fleet_vehicles ===


class FleetVehicle(Base):
    """Vehicle master record."""

    __tablename__ = "fleet_vehicles"

    vehicle_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    asset_code: Mapped[str] = mapped_column(String(50), nullable=False)
    plate_raw_current: Mapped[str] = mapped_column(String(32), nullable=False)
    normalized_plate_current: Mapped[str] = mapped_column(String(32), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(80))
    model: Mapped[str | None] = mapped_column(String(80))
    model_year: Mapped[int | None] = mapped_column(SmallInteger)
    ownership_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    row_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    spec_stream_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    is_selectable: Mapped[bool | None] = mapped_column(
        Boolean,
        Computed("status = 'ACTIVE' AND soft_deleted_at_utc IS NULL"),
    )
    created_at_utc: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_by_actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at_utc: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by_actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    updated_by_actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    soft_deleted_at_utc: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    soft_deleted_by_actor_type: Mapped[str | None] = mapped_column(String(20))
    soft_deleted_by_actor_id: Mapped[str | None] = mapped_column(String(64))
    soft_delete_reason: Mapped[str | None] = mapped_column(Text)

    # Relationships
    spec_versions: Mapped[list[FleetVehicleSpecVersion]] = relationship(back_populates="vehicle", lazy="raise")

    @property
    def lifecycle_state(self) -> str:
        """Derive lifecycle state from status + soft_deleted_at_utc."""
        if self.soft_deleted_at_utc is not None:
            return "SOFT_DELETED"
        return self.status


# === 8.3 fleet_trailers ===


class FleetTrailer(Base):
    """Trailer master record."""

    __tablename__ = "fleet_trailers"

    trailer_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    asset_code: Mapped[str] = mapped_column(String(50), nullable=False)
    plate_raw_current: Mapped[str] = mapped_column(String(32), nullable=False)
    normalized_plate_current: Mapped[str] = mapped_column(String(32), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(80))
    model: Mapped[str | None] = mapped_column(String(80))
    model_year: Mapped[int | None] = mapped_column(SmallInteger)
    ownership_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    row_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    spec_stream_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    is_selectable: Mapped[bool | None] = mapped_column(
        Boolean,
        Computed("status = 'ACTIVE' AND soft_deleted_at_utc IS NULL"),
    )
    created_at_utc: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_by_actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at_utc: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by_actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    updated_by_actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    soft_deleted_at_utc: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    soft_deleted_by_actor_type: Mapped[str | None] = mapped_column(String(20))
    soft_deleted_by_actor_id: Mapped[str | None] = mapped_column(String(64))
    soft_delete_reason: Mapped[str | None] = mapped_column(Text)

    # Relationships
    spec_versions: Mapped[list[FleetTrailerSpecVersion]] = relationship(back_populates="trailer", lazy="raise")

    @property
    def lifecycle_state(self) -> str:
        """Derive lifecycle state from status + soft_deleted_at_utc."""
        if self.soft_deleted_at_utc is not None:
            return "SOFT_DELETED"
        return self.status


# === 8.4 fleet_vehicle_spec_versions ===


class FleetVehicleSpecVersion(Base):
    """Vehicle technical spec version (time-versioned)."""

    __tablename__ = "fleet_vehicle_spec_versions"

    vehicle_spec_version_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    vehicle_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("fleet_vehicles.vehicle_id", ondelete="RESTRICT"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from_utc: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to_utc: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # Technical spec fields
    fuel_type: Mapped[str | None] = mapped_column(String(16))
    powertrain_type: Mapped[str | None] = mapped_column(String(20))
    engine_power_kw: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    engine_displacement_l: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    emission_class: Mapped[str | None] = mapped_column(String(16))
    transmission_type: Mapped[str | None] = mapped_column(String(16))
    gear_count: Mapped[int | None] = mapped_column(SmallInteger)
    final_drive_ratio: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    axle_config: Mapped[str | None] = mapped_column(String(8))
    total_axle_count: Mapped[int | None] = mapped_column(SmallInteger)
    driven_axle_count: Mapped[int | None] = mapped_column(SmallInteger)
    curb_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    gvwr_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    gcwr_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    payload_capacity_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    tractor_cab_type: Mapped[str | None] = mapped_column(String(16))
    roof_height_class: Mapped[str | None] = mapped_column(String(16))
    aero_package_level: Mapped[str | None] = mapped_column(String(16))
    tire_rr_class: Mapped[str | None] = mapped_column(String(16))
    tire_type: Mapped[str | None] = mapped_column(String(16))
    speed_limiter_kph: Mapped[int | None] = mapped_column(SmallInteger)
    pto_present: Mapped[bool | None] = mapped_column(Boolean)
    apu_present: Mapped[bool | None] = mapped_column(Boolean)
    idle_reduction_type: Mapped[str | None] = mapped_column(String(16))
    first_registration_date: Mapped[datetime.date | None] = mapped_column(Date)
    in_service_date: Mapped[datetime.date | None] = mapped_column(Date)
    change_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at_utc: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_by_actor_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # Relationships
    vehicle: Mapped[FleetVehicle] = relationship(back_populates="spec_versions")


# === 8.5 fleet_trailer_spec_versions ===


class FleetTrailerSpecVersion(Base):
    """Trailer technical spec version (time-versioned)."""

    __tablename__ = "fleet_trailer_spec_versions"

    trailer_spec_version_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    trailer_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("fleet_trailers.trailer_id", ondelete="RESTRICT"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from_utc: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to_utc: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # Trailer spec fields
    trailer_type: Mapped[str | None] = mapped_column(String(24))
    body_type: Mapped[str | None] = mapped_column(String(24))
    tare_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    max_payload_kg: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    axle_count: Mapped[int | None] = mapped_column(SmallInteger)
    lift_axle_present: Mapped[bool | None] = mapped_column(Boolean)
    body_height_mm: Mapped[int | None] = mapped_column(Integer)
    body_length_mm: Mapped[int | None] = mapped_column(Integer)
    body_width_mm: Mapped[int | None] = mapped_column(Integer)
    tire_rr_class: Mapped[str | None] = mapped_column(String(16))
    tire_type: Mapped[str | None] = mapped_column(String(16))
    side_skirts_present: Mapped[bool | None] = mapped_column(Boolean)
    rear_tail_present: Mapped[bool | None] = mapped_column(Boolean)
    gap_reducer_present: Mapped[bool | None] = mapped_column(Boolean)
    wheel_covers_present: Mapped[bool | None] = mapped_column(Boolean)
    reefer_unit_present: Mapped[bool | None] = mapped_column(Boolean)
    reefer_unit_type: Mapped[str | None] = mapped_column(String(24))
    reefer_power_source: Mapped[str | None] = mapped_column(String(24))
    aero_package_level: Mapped[str | None] = mapped_column(String(16))
    change_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at_utc: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_by_actor_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # Relationships
    trailer: Mapped[FleetTrailer] = relationship(back_populates="spec_versions")


# === 8.6 fleet_asset_timeline_events ===


class FleetAssetTimelineEvent(Base):
    """Immutable business timeline event. Survives hard-delete (no FK)."""

    __tablename__ = "fleet_asset_timeline_events"

    event_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    aggregate_type: Mapped[str] = mapped_column(String(16), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(26), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64))
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    occurred_at_utc: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


# === 8.7 fleet_asset_delete_audit ===


class FleetAssetDeleteAudit(Base):
    """Immutable delete audit log. Survives hard-delete (no FK)."""

    __tablename__ = "fleet_asset_delete_audit"

    delete_audit_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    aggregate_type: Mapped[str] = mapped_column(String(16), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(26), nullable=False)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reference_check_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reference_check_status: Mapped[str] = mapped_column(String(32), nullable=False)
    delete_attempted_by_actor_type: Mapped[str] = mapped_column(String(20), nullable=False)
    delete_attempted_by_actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    delete_result: Mapped[str] = mapped_column(String(64), nullable=False)
    delete_result_reason: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at_utc: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FleetAuditLogModel(Base):
    """General high-fidelity audit log for Fleet Service mutations."""

    __tablename__ = "fleet_audit_log"

    audit_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    aggregate_type: Mapped[str] = mapped_column(String(16), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(26), nullable=False)
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_fields_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    old_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    new_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at_utc: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_fleet_audit_log_agg_created", "aggregate_type", "aggregate_id", "created_at_utc"),)


# === 8.8 fleet_outbox ===


class FleetOutbox(Base):
    """Transactional outbox event queue."""

    __tablename__ = "fleet_outbox"

    outbox_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    aggregate_type: Mapped[str] = mapped_column(String(16), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(26), nullable=False)
    causation_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    event_name: Mapped[str] = mapped_column(String(80), nullable=False)
    event_version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    partition_key: Mapped[str | None] = mapped_column(String(100))
    publish_status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    next_attempt_at_utc: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claim_token: Mapped[str | None] = mapped_column(String(50))
    claim_expires_at_utc: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_by_worker: Mapped[str | None] = mapped_column(String(50))
    created_at_utc: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at_utc: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_fleet_outbox_partition", "partition_key", "publish_status", "created_at_utc"),
        Index("ix_fleet_outbox_status_retry", "publish_status", "next_attempt_at_utc", "created_at_utc"),
    )


# === 8.9 fleet_idempotency_records ===


class FleetIdempotencyRecord(Base):
    """Idempotency record for create-replay protection."""

    __tablename__ = "fleet_idempotency_records"

    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    endpoint_fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    resource_type: Mapped[str] = mapped_column(String(16), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(26), nullable=False)
    created_at_utc: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at_utc: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# === 8.10 fleet_worker_heartbeats ===


class FleetWorkerHeartbeat(Base):
    """Worker heartbeat for readiness probe."""

    __tablename__ = "fleet_worker_heartbeats"

    worker_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    recorded_at_utc: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
