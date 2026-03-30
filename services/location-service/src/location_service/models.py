import uuid
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from location_service.enums import (
    BulkRefreshItemStatus,
    BulkRefreshStatus,
    DirectionCode,
    GradeClass,
    PairStatus,
    ProcessingStatus,
    RoadClass,
    RunStatus,
    SpeedBand,
    SpeedLimitState,
    TriggerType,
    UrbanClass,
    ValidationResult,
)


def get_utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class LocationPoint(Base):
    __tablename__ = "location_points"

    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name_tr: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name_tr: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    normalized_name_en: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    latitude_6dp: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    longitude_6dp: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"), nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_utcnow, nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utcnow, onupdate=get_utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("latitude_6dp", "longitude_6dp", name="uq_location_points_lat_lng"),
        CheckConstraint("latitude_6dp >= -90.0 AND latitude_6dp <= 90.0", name="chk_location_points_lat"),
        CheckConstraint("longitude_6dp >= -180.0 AND longitude_6dp <= 180.0", name="chk_location_points_lng"),
        CheckConstraint("NOT (latitude_6dp = 0.0 AND longitude_6dp = 0.0)", name="chk_location_points_not_null_island"),
        CheckConstraint("code ~ '^[A-Z0-9_]{2,32}$'", name="chk_location_points_code_format"),
    )


class RoutePair(Base):
    __tablename__ = "route_pairs"

    route_pair_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pair_code: Mapped[str] = mapped_column(String(29), unique=True, nullable=False)  # Format RP_<ULID>
    origin_location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("location_points.location_id"), nullable=False)
    destination_location_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("location_points.location_id"), nullable=False
    )
    profile_code: Mapped[str] = mapped_column(String(32), default="TIR", server_default="TIR", nullable=False)
    pair_status: Mapped[PairStatus] = mapped_column(String(50), nullable=False)

    forward_route_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("routes.route_id", use_alter=True), nullable=True
    )
    reverse_route_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("routes.route_id", use_alter=True), nullable=True
    )

    current_active_forward_version_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_active_reverse_version_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pending_forward_version_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pending_reverse_version_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_utcnow, nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utcnow, onupdate=get_utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint("origin_location_id != destination_location_id", name="chk_route_pairs_origin_neq_dest"),
        CheckConstraint("pair_code ~ '^RP_[0-9A-Z]{26}$'", name="chk_route_pairs_pair_code_format"),
        CheckConstraint(
            """
            (pending_forward_version_no IS NULL AND pending_reverse_version_no IS NULL) OR
            (pending_forward_version_no IS NOT NULL AND pending_reverse_version_no IS NOT NULL)
            """,
            name="chk_route_pairs_pending_pointers_atomic",
        ),
        Index(
            "idx_route_pairs_live_unique",
            "origin_location_id",
            "destination_location_id",
            "profile_code",
            unique=True,
            postgresql_where=text("pair_status IN ('ACTIVE', 'DRAFT')"),
        ),
    )


class Route(Base):
    __tablename__ = "routes"

    route_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    route_pair_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("route_pairs.route_pair_id"), nullable=False)
    route_code: Mapped[str] = mapped_column(String(31), unique=True, nullable=False)
    direction: Mapped[DirectionCode] = mapped_column(String(20), nullable=False)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_utcnow, nullable=False)


class RouteVersionCounter(Base):
    __tablename__ = "route_version_counters"

    route_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("routes.route_id"), primary_key=True)
    next_version_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_utcnow, nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utcnow, onupdate=get_utcnow, nullable=False
    )


class RouteVersion(Base):
    __tablename__ = "route_versions"

    route_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("routes.route_id"), primary_key=True)
    version_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    processing_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("processing_runs.processing_run_id"), nullable=True
    )
    processing_status: Mapped[ProcessingStatus] = mapped_column(String(50), nullable=False)

    total_distance_m: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    total_duration_s: Mapped[int] = mapped_column(Integer, nullable=False)
    total_ascent_m: Mapped[Optional[float]] = mapped_column(Numeric(10, 4), nullable=True)
    total_descent_m: Mapped[Optional[float]] = mapped_column(Numeric(10, 4), nullable=True)

    avg_grade_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    max_grade_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    steepest_downhill_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)

    known_speed_limit_ratio: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    segment_count: Mapped[int] = mapped_column(Integer, nullable=False)

    validation_result: Mapped[ValidationResult] = mapped_column(String(50), nullable=False)
    distance_validation_delta_pct: Mapped[Optional[float]] = mapped_column(Numeric(6, 3), nullable=True)
    duration_validation_delta_pct: Mapped[Optional[float]] = mapped_column(Numeric(6, 3), nullable=True)
    endpoint_validation_delta_m: Mapped[Optional[float]] = mapped_column(Numeric(8, 2), nullable=True)

    field_origin_matrix_json: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    field_origin_matrix_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    road_type_distribution_json: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    speed_limit_distribution_json: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    urban_distribution_json: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    warnings_json: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)

    refresh_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    processing_algorithm_version: Mapped[str] = mapped_column(String(50), nullable=False)

    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_utcnow, nullable=False)
    activated_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index(
            "idx_route_versions_active_unique",
            "route_id",
            unique=True,
            postgresql_where=text("processing_status = 'ACTIVE'"),
        ),
        CheckConstraint("segment_count >= 1", name="chk_route_versions_segment_count"),
        CheckConstraint("total_distance_m >= 0", name="chk_route_versions_total_distance"),
        CheckConstraint("total_duration_s >= 0", name="chk_route_versions_total_duration"),
    )


class RouteSegment(Base):
    __tablename__ = "route_segments"

    route_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    version_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    segment_no: Mapped[int] = mapped_column(Integer, primary_key=True)

    start_latitude_6dp: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    start_longitude_6dp: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    end_latitude_6dp: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    end_longitude_6dp: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)

    distance_m: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)

    start_elevation_m: Mapped[Optional[float]] = mapped_column(Numeric(8, 2), nullable=True)
    end_elevation_m: Mapped[Optional[float]] = mapped_column(Numeric(8, 2), nullable=True)
    grade_pct: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)

    grade_class: Mapped[GradeClass] = mapped_column(String(50), nullable=False)
    road_class: Mapped[RoadClass] = mapped_column(String(50), nullable=False)
    urban_class: Mapped[UrbanClass] = mapped_column(String(50), nullable=False)

    speed_limit_kph: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    speed_limit_state: Mapped[SpeedLimitState] = mapped_column(String(50), nullable=False)
    speed_band: Mapped[SpeedBand] = mapped_column(String(50), nullable=False)

    tunnel_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["route_id", "version_no"],
            ["route_versions.route_id", "route_versions.version_no"],
            name="fk_route_segments_version",
        ),
        CheckConstraint("distance_m >= 0", name="chk_route_segments_distance"),
        CheckConstraint("segment_no >= 1", name="chk_route_segments_segment_no"),
    )


class ProcessingRun(Base):
    __tablename__ = "processing_runs"

    processing_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    route_pair_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("route_pairs.route_pair_id"), nullable=False)
    run_status: Mapped[RunStatus] = mapped_column(String(50), nullable=False)
    trigger_type: Mapped[TriggerType] = mapped_column(String(50), nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)

    provider_mapbox_status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    provider_ors_status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    claim_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    claim_expires_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_by_worker: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    expected_forward_version_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expected_reverse_version_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    bulk_refresh_job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("bulk_refresh_jobs.bulk_refresh_job_id"), nullable=True
    )
    started_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_utcnow, nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utcnow, onupdate=get_utcnow, nullable=False
    )

    __table_args__ = (
        Index(
            "idx_processing_runs_queued_running_unique",
            "route_pair_id",
            unique=True,
            postgresql_where=text("run_status IN ('QUEUED', 'RUNNING')"),
        ),
        CheckConstraint(
            "provider_mapbox_status IN ('PENDING', 'OK', 'FAILED')", name="chk_processing_runs_mapbox_status"
        ),
        CheckConstraint(
            "provider_ors_status IN ('PENDING', 'OK', 'FAILED', 'UNAVAILABLE')", name="chk_processing_runs_ors_status"
        ),
    )


class RouteUsageRef(Base):
    __tablename__ = "route_usage_refs"

    route_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    version_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    consumer_service: Mapped[str] = mapped_column(String(100), primary_key=True)
    consumer_entity_type: Mapped[str] = mapped_column(String(100), primary_key=True)
    consumer_entity_id: Mapped[str] = mapped_column(String(100), primary_key=True)

    consumer_reported_used_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_utcnow, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["route_id", "version_no"],
            ["route_versions.route_id", "route_versions.version_no"],
            ondelete="RESTRICT",
            name="fk_route_usage_refs_version",
        ),
    )


class BulkRefreshJob(Base):
    __tablename__ = "bulk_refresh_jobs"

    bulk_refresh_job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_status: Mapped[BulkRefreshStatus] = mapped_column(String(50), nullable=False)
    trigger_type: Mapped[TriggerType] = mapped_column(String(50), nullable=False)
    selection_scope_json: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)

    total_pairs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_pairs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_pairs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    skipped_pairs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    started_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_utcnow, nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utcnow, onupdate=get_utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint("total_pairs >= 0", name="chk_bulk_refresh_jobs_total"),
        CheckConstraint("processed_pairs >= 0", name="chk_bulk_refresh_jobs_processed"),
        CheckConstraint("failed_pairs >= 0", name="chk_bulk_refresh_jobs_failed"),
        CheckConstraint("skipped_pairs >= 0", name="chk_bulk_refresh_jobs_skipped"),
    )


class BulkRefreshJobItem(Base):
    __tablename__ = "bulk_refresh_job_items"

    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bulk_refresh_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bulk_refresh_jobs.bulk_refresh_job_id", ondelete="CASCADE"), nullable=False
    )
    item_no: Mapped[int] = mapped_column(Integer, nullable=False)
    route_pair_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("route_pairs.route_pair_id", ondelete="SET NULL"), nullable=True
    )
    item_status: Mapped[BulkRefreshItemStatus] = mapped_column(String(50), nullable=False)
    processing_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("processing_runs.processing_run_id", ondelete="SET NULL"), nullable=True
    )
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_utcnow, nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utcnow, onupdate=get_utcnow, nullable=False
    )

    __table_args__ = (UniqueConstraint("bulk_refresh_job_id", "item_no", name="uq_bulk_refresh_job_items_no"),)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    locked_at_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    response_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_headers_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    response_body: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    response_truncated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    canonical_request_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    expires_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=get_utcnow, nullable=False)
