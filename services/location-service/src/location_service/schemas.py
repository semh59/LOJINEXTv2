"""Shared Pydantic v2 schemas for Location Service.

Base schemas, pagination wrappers, and common response shapes.
Full endpoint-specific schemas will be added in TASK-0005.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field


class LocationBaseModel(BaseModel):
    """Base model with shared config for all Location Service schemas."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ---------------------------------------------------------------------------
# Pagination (Section 7 common rules)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Common response shapes
# ---------------------------------------------------------------------------


class TimestampMixin(LocationBaseModel):
    """Mixin for created/updated timestamps."""

    created_at_utc: datetime
    updated_at_utc: datetime


class AuditMixin(LocationBaseModel):
    """Mixin for created_by / updated_by fields."""

    created_by: str
    updated_by: str


# ---------------------------------------------------------------------------
# Location Point Schemas (Section 7.1 - 7.4)
# ---------------------------------------------------------------------------


class PointCreate(LocationBaseModel):
    """Payload for POST /v1/location/points."""

    code: str
    name_tr: str
    name_en: str
    latitude_6dp: float
    longitude_6dp: float
    is_active: bool = True


class PointUpdate(LocationBaseModel):
    """Payload for PATCH /v1/location/points/{id}."""

    name_tr: str | None = None
    name_en: str | None = None
    latitude_6dp: float | None = None
    longitude_6dp: float | None = None
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


# ---------------------------------------------------------------------------
# Route Pair Schemas (Section 7.6 - 7.9)
# ---------------------------------------------------------------------------


class PairCreateRequest(LocationBaseModel):
    """Payload for POST /v1/location/route-pairs."""

    origin_code: str
    destination_code: str
    language_hint: str = "auto"
    is_active: bool = True


class PairUpdateRequest(LocationBaseModel):
    """Payload for PATCH /v1/pairs/{id}."""

    is_active: bool | None = None
    profile_code: str | None = None


class PairResponse(TimestampMixin, LocationBaseModel):
    """Response shape for Location Route Pair endpoints."""

    pair_id: UUID = Field(validation_alias="route_pair_id")
    pair_code: str
    status: str = Field(validation_alias="pair_status")
    origin_location_id: UUID
    destination_location_id: UUID

    @computed_field
    def is_active(self) -> bool:
        return self.status == "ACTIVE"

    active_forward_version_no: int | None = Field(None, validation_alias="current_active_forward_version_no")
    active_reverse_version_no: int | None = Field(None, validation_alias="current_active_reverse_version_no")
    draft_forward_version_no: int | None = Field(None, validation_alias="pending_forward_version_no")
    draft_reverse_version_no: int | None = Field(None, validation_alias="pending_reverse_version_no")

    row_version: int


class PairListResponse(PaginatedResponse):
    """Paginated list of pairs."""

    data: list[PairResponse]


# ---------------------------------------------------------------------------
# Processing Schemas (Section 7.10)
# ---------------------------------------------------------------------------


class CalculateRequest(LocationBaseModel):
    """Payload for POST /v1/pairs/{id}/calculate."""

    force_refresh: bool = False


class ProcessingRunResponse(TimestampMixin, LocationBaseModel):
    """Response shape for Processing Run endpoints."""

    run_id: UUID
    pair_id: UUID
    trigger_type: str
    run_status: str
    error_message: str | None = None
    started_at_utc: datetime | None = None
    completed_at_utc: datetime | None = None
