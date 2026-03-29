"""Shared Pydantic v2 schemas for Location Service."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

from location_service.enums import DirectionCode, ProcessingStatus, RunStatus, TriggerType, ValidationResult


class LocationBaseModel(BaseModel):
    """Base model with shared config for all Location Service schemas."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, extra="forbid")


class ProfileCode(StrEnum):
    """Public profile code contract for frontend-facing APIs."""

    TIR = "TIR"
    VAN = "VAN"


class PaginationMeta(LocationBaseModel):
    """Pagination metadata returned in list responses."""

    page: int
    per_page: int
    total_items: int
    total_pages: int
    sort: str


class PaginatedResponse(LocationBaseModel):
    """Generic paginated response wrapper."""

    data: list[Any]
    meta: PaginationMeta


class TimestampMixin(LocationBaseModel):
    """Mixin for created/updated timestamps."""

    created_at_utc: datetime
    updated_at_utc: datetime


class AuditMixin(LocationBaseModel):
    """Mixin for created_by / updated_by fields."""

    created_by: str
    updated_by: str


class PointCreate(LocationBaseModel):
    """Payload for POST /v1/points."""

    code: str
    name_tr: str
    name_en: str
    latitude_6dp: float
    longitude_6dp: float
    is_active: bool = True


class PointUpdate(LocationBaseModel):
    """Payload for PATCH /v1/points/{id}."""

    name_tr: str | None = None
    name_en: str | None = None
    is_active: bool | None = None


class PointResponse(TimestampMixin, PointCreate):
    """Response shape for Location Point endpoints."""

    location_id: UUID
    normalized_name_tr: str
    normalized_name_en: str
    row_version: int


class PointListResponse(PaginatedResponse):
    """Paginated list of points."""

    data: list[PointResponse]


class PairCreateRequest(LocationBaseModel):
    """Payload for POST /v1/pairs."""

    origin_code: str
    destination_code: str
    profile_code: ProfileCode = ProfileCode.TIR


class PairUpdateRequest(LocationBaseModel):
    """Payload for PATCH /v1/pairs/{id}."""

    profile_code: ProfileCode | None = None


class PairResponse(TimestampMixin, LocationBaseModel):
    """Response shape for route pair endpoints."""

    pair_id: UUID = Field(validation_alias="route_pair_id")
    pair_code: str
    status: str = Field(validation_alias="pair_status")
    origin_location_id: UUID
    destination_location_id: UUID
    profile_code: ProfileCode
    origin_code: str
    origin_name_tr: str
    origin_name_en: str
    destination_code: str
    destination_name_tr: str
    destination_name_en: str
    forward_route_id: UUID | None = None
    reverse_route_id: UUID | None = None

    @computed_field
    def is_active(self) -> bool:
        return self.status == "ACTIVE"

    active_forward_version_no: int | None = Field(None, validation_alias="current_active_forward_version_no")
    active_reverse_version_no: int | None = Field(None, validation_alias="current_active_reverse_version_no")
    draft_forward_version_no: int | None = Field(None, validation_alias="pending_forward_version_no")
    draft_reverse_version_no: int | None = Field(None, validation_alias="pending_reverse_version_no")

    @computed_field
    def has_pending_draft(self) -> bool:
        return self.draft_forward_version_no is not None and self.draft_reverse_version_no is not None

    row_version: int


class PairListResponse(PaginatedResponse):
    """Paginated list of pairs."""

    data: list[PairResponse]


class CalculateRequest(LocationBaseModel):
    """Payload for POST /v1/pairs/{id}/calculate."""

    pass


class ProcessingRunResponse(TimestampMixin, LocationBaseModel):
    """Response shape for processing run endpoints."""

    run_id: UUID = Field(validation_alias="processing_run_id")
    pair_id: UUID = Field(validation_alias="route_pair_id")
    pair_code: str
    trigger_type: TriggerType
    run_status: RunStatus
    attempt_no: int
    provider_mapbox_status: str
    provider_ors_status: str
    error_message: str | None = None
    started_at_utc: datetime | None = None
    completed_at_utc: datetime | None = None


class ProcessingRunListResponse(PaginatedResponse):
    """Paginated list of processing runs for a pair."""

    data: list[ProcessingRunResponse]


class RouteVersionDetailResponse(LocationBaseModel):
    """Frontend-facing route version detail payload."""

    route_id: UUID
    route_code: str
    pair_id: UUID
    pair_code: str
    direction: DirectionCode
    version_no: int
    processing_status: ProcessingStatus
    total_distance_m: float
    total_duration_s: int
    total_ascent_m: float | None = None
    total_descent_m: float | None = None
    avg_grade_pct: float | None = None
    max_grade_pct: float | None = None
    steepest_downhill_pct: float | None = None
    known_speed_limit_ratio: float
    segment_count: int
    validation_result: ValidationResult
    distance_validation_delta_pct: float | None = None
    duration_validation_delta_pct: float | None = None
    endpoint_validation_delta_m: float | None = None
    road_type_distribution_json: dict[str, Any]
    speed_limit_distribution_json: dict[str, Any]
    urban_distribution_json: dict[str, Any]
    warnings_json: list[str]
    refresh_reason: str | None = None
    processing_algorithm_version: str
    created_at_utc: datetime
    activated_at_utc: datetime | None = None


class RouteGeometryResponse(LocationBaseModel):
    """Frontend-facing 2D geometry payload for a route version."""

    route_id: UUID
    version_no: int
    direction: DirectionCode
    coordinate_count: int
    coordinates: list[list[float]]


class BulkRefreshTriggerRequest(LocationBaseModel):
    """Request payload for triggering bulk refresh."""

    pair_ids: list[UUID] | None = None


class BulkRefreshTriggerResponse(LocationBaseModel):
    """Stable response payload for bulk refresh triggers."""

    status: str
    triggered_count: int
    requested_pair_count: int | None = None
    detail: str


class InternalRouteResolveRequest(LocationBaseModel):
    """Payload for POST /internal/v1/routes/resolve."""

    origin_name: str = Field(min_length=1)
    destination_name: str = Field(min_length=1)
    profile_code: ProfileCode = ProfileCode.TIR
    language_hint: Literal["AUTO", "TR", "EN"] = "AUTO"


class InternalRouteResolveResponse(LocationBaseModel):
    """Resolved route identity returned to trip-service."""

    route_id: UUID
    pair_id: UUID
    resolution: Literal["EXACT_TR", "EXACT_EN"]


class InternalTripContextResponse(LocationBaseModel):
    """Active forward/reverse trip context for a route pair."""

    pair_id: UUID
    origin_location_id: UUID
    origin_name: str
    destination_location_id: UUID
    destination_name: str
    forward_route_id: UUID
    forward_duration_s: int
    reverse_route_id: UUID
    reverse_duration_s: int
    profile_code: ProfileCode
    pair_status: str
