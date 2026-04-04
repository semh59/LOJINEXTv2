"""Pydantic response DTOs for Fleet Service API contracts (Section 9)."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field  # noqa: I001

# --- Pagination ---


class PagedResponse(BaseModel):
    """Offset-based paginated response for list endpoints."""

    items: list[Any]
    page: int
    per_page: int
    total: int
    total_pages: int


class CursorResponse(BaseModel):
    """Cursor-based paginated response for selectable endpoints."""

    items: list[Any]
    next_cursor: str | None = None
    has_more: bool = False


# --- Vehicle ---


class CurrentSpecSummary(BaseModel):
    """Lightweight spec summary for vehicle/trailer detail response."""

    version_no: int
    fuel_type: str | None = None
    powertrain_type: str | None = None
    emission_class: str | None = None
    curb_weight_kg: Decimal | None = None
    gvwr_kg: Decimal | None = None
    effective_from_utc: datetime.datetime | None = None


class VehicleDetailResponse(BaseModel):
    """GET /api/v1/vehicles/{id} — Full vehicle detail (Section 9.3)."""

    vehicle_id: str
    asset_code: str
    plate_raw_current: str
    normalized_plate_current: str
    brand: str | None = None
    model: str | None = None
    model_year: int | None = None
    ownership_type: str
    status: str
    lifecycle_state: str
    notes: str | None = None
    row_version: int
    spec_stream_version: int
    is_selectable: bool | None = None
    current_spec_summary: CurrentSpecSummary | None = None
    created_at_utc: datetime.datetime
    created_by_actor_type: str
    created_by_actor_id: str
    updated_at_utc: datetime.datetime
    updated_by_actor_type: str
    updated_by_actor_id: str
    soft_deleted_at_utc: datetime.datetime | None = None
    soft_deleted_by_actor_type: str | None = None
    soft_deleted_by_actor_id: str | None = None
    soft_delete_reason: str | None = None


class VehicleListItemResponse(BaseModel):
    """GET /api/v1/vehicles — Lighter list item (no notes, no soft_delete details)."""

    vehicle_id: str
    asset_code: str
    plate_raw_current: str
    normalized_plate_current: str
    brand: str | None = None
    model: str | None = None
    model_year: int | None = None
    ownership_type: str
    status: str
    lifecycle_state: str
    row_version: int
    spec_stream_version: int
    is_selectable: bool | None = None
    created_at_utc: datetime.datetime
    updated_at_utc: datetime.datetime


# --- Trailer ---


class TrailerCurrentSpecSummary(BaseModel):
    """Lightweight spec summary for trailer detail response."""

    version_no: int
    trailer_type: str | None = None
    body_type: str | None = None
    tare_weight_kg: Decimal | None = None
    max_payload_kg: Decimal | None = None
    effective_from_utc: datetime.datetime | None = None


class TrailerDetailResponse(BaseModel):
    """GET /api/v1/trailers/{id} — Full trailer detail."""

    trailer_id: str
    asset_code: str
    plate_raw_current: str
    normalized_plate_current: str
    brand: str | None = None
    model: str | None = None
    model_year: int | None = None
    ownership_type: str
    status: str
    lifecycle_state: str
    notes: str | None = None
    row_version: int
    spec_stream_version: int
    is_selectable: bool | None = None
    current_spec_summary: TrailerCurrentSpecSummary | None = None
    created_at_utc: datetime.datetime
    created_by_actor_type: str
    created_by_actor_id: str
    updated_at_utc: datetime.datetime
    updated_by_actor_type: str
    updated_by_actor_id: str
    soft_deleted_at_utc: datetime.datetime | None = None
    soft_deleted_by_actor_type: str | None = None
    soft_deleted_by_actor_id: str | None = None
    soft_delete_reason: str | None = None


class TrailerListItemResponse(BaseModel):
    """GET /api/v1/trailers — Lighter list item."""

    trailer_id: str
    asset_code: str
    plate_raw_current: str
    normalized_plate_current: str
    brand: str | None = None
    model: str | None = None
    model_year: int | None = None
    ownership_type: str
    status: str
    lifecycle_state: str
    row_version: int
    spec_stream_version: int
    is_selectable: bool | None = None
    created_at_utc: datetime.datetime
    updated_at_utc: datetime.datetime


# --- Vehicle Spec ---


class VehicleSpecResponse(BaseModel):
    """Vehicle spec version full response (Section 9)."""

    vehicle_spec_version_id: str
    vehicle_id: str
    version_no: int
    effective_from_utc: datetime.datetime
    effective_to_utc: datetime.datetime | None = None
    is_current: bool
    fuel_type: str | None = None
    powertrain_type: str | None = None
    engine_power_kw: Decimal | None = None
    engine_displacement_l: Decimal | None = None
    emission_class: str | None = None
    transmission_type: str | None = None
    gear_count: int | None = None
    final_drive_ratio: Decimal | None = None
    axle_config: str | None = None
    total_axle_count: int | None = None
    driven_axle_count: int | None = None
    curb_weight_kg: Decimal | None = None
    gvwr_kg: Decimal | None = None
    gcwr_kg: Decimal | None = None
    payload_capacity_kg: Decimal | None = None
    tractor_cab_type: str | None = None
    roof_height_class: str | None = None
    aero_package_level: str | None = None
    tire_rr_class: str | None = None
    tire_type: str | None = None
    speed_limiter_kph: int | None = None
    pto_present: bool | None = None
    apu_present: bool | None = None
    idle_reduction_type: str | None = None
    first_registration_date: datetime.date | None = None
    in_service_date: datetime.date | None = None
    change_reason: str
    created_at_utc: datetime.datetime
    created_by_actor_type: str
    created_by_actor_id: str


# --- Trailer Spec ---


class TrailerSpecResponse(BaseModel):
    """Trailer spec version full response."""

    trailer_spec_version_id: str
    trailer_id: str
    version_no: int
    effective_from_utc: datetime.datetime
    effective_to_utc: datetime.datetime | None = None
    is_current: bool
    trailer_type: str | None = None
    body_type: str | None = None
    tare_weight_kg: Decimal | None = None
    max_payload_kg: Decimal | None = None
    axle_count: int | None = None
    lift_axle_present: bool | None = None
    body_height_mm: int | None = None
    body_length_mm: int | None = None
    body_width_mm: int | None = None
    tire_rr_class: str | None = None
    tire_type: str | None = None
    side_skirts_present: bool | None = None
    rear_tail_present: bool | None = None
    gap_reducer_present: bool | None = None
    wheel_covers_present: bool | None = None
    reefer_unit_present: bool | None = None
    reefer_unit_type: str | None = None
    reefer_power_source: str | None = None
    aero_package_level: str | None = None
    change_reason: str
    created_at_utc: datetime.datetime
    created_by_actor_type: str
    created_by_actor_id: str


# --- Validate ---


class ValidateResponse(BaseModel):
    """GET /internal/v1/{asset_type}/{id}/validate — Always 200."""

    exists: bool
    status: str | None = None
    lifecycle_state: str | None = None
    is_selectable: bool | None = None
    is_usable_for_new_operation: bool | None = None
    reason_code: str | None = None


class ValidateBulkItemResponse(BaseModel):
    """Single item in bulk-validate response."""

    asset_id: str
    asset_type: str
    exists: bool
    status: str | None = None
    lifecycle_state: str | None = None
    is_selectable: bool | None = None
    is_usable_for_new_operation: bool | None = None
    reason_code: str | None = None


# --- Selectable ---


class SelectableItemResponse(BaseModel):
    """GET /internal/v1/selectable/{vehicles|trailers} — Selectable item."""

    asset_id: str
    asset_code: str
    plate_raw_current: str
    normalized_plate_current: str
    brand: str | None = None
    model: str | None = None
    model_year: int | None = None


# --- Fuel Metadata ---


class FuelMetadataSpecResponse(BaseModel):
    """Fuel metadata spec DTO for resolve endpoint."""

    fuel_type: str | None = None
    powertrain_type: str | None = None
    emission_class: str | None = None
    engine_power_kw: Decimal | None = None
    curb_weight_kg: Decimal | None = None
    gvwr_kg: Decimal | None = None
    aero_package_level: str | None = None
    tire_rr_class: str | None = None


class FuelMetadataTrailerSpecResponse(BaseModel):
    """Fuel metadata trailer spec DTO for resolve endpoint."""

    trailer_type: str | None = None
    tare_weight_kg: Decimal | None = None
    max_payload_kg: Decimal | None = None
    axle_count: int | None = None
    aero_package_level: str | None = None
    tire_rr_class: str | None = None
    reefer_unit_present: bool | None = None
    reefer_unit_type: str | None = None
    reefer_power_source: str | None = None


class DerivedCombination(BaseModel):
    """Derived combination formulas (Section 5)."""

    combined_empty_weight_kg: Decimal | None = None
    combined_axle_count: int | None = None
    reefer_present: bool = False
    aero_package_level: str | None = None


class FuelMetadataResolveResponse(BaseModel):
    """POST /internal/v1/assets/fuel-metadata/resolve response."""

    vehicle: FuelMetadataSpecResponse | None = None
    trailer: FuelMetadataTrailerSpecResponse | None = None
    derived_combination: DerivedCombination | None = None


# --- Hard Delete ---


class HardDeleteResponse(BaseModel):
    """POST hard-delete success response."""

    deleted: bool = True
    aggregate_type: str
    aggregate_id: str
    delete_audit_id: str


# --- Timeline ---


class TimelineEventResponse(BaseModel):
    """GET timeline event item."""

    event_id: str
    aggregate_type: str
    aggregate_id: str
    event_type: str
    actor_type: str
    actor_id: str
    request_id: str | None = None
    correlation_id: str | None = None
    occurred_at_utc: datetime.datetime
    payload: dict[str, Any] = Field(default_factory=dict)
