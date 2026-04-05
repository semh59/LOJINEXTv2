"""Pydantic request DTOs for Fleet Service API contracts (Section 9)."""

from __future__ import annotations

import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

# --- Vehicle ---


class VehicleCreateRequest(BaseModel):
    """POST /api/v1/vehicles — Create a vehicle (Section 9.1)."""

    asset_code: str = Field(..., min_length=1, max_length=50)
    plate: str = Field(..., min_length=1, max_length=32)
    ownership_type: str = Field(..., pattern=r"^(OWNED|LEASED|THIRD_PARTY)$")
    brand: str | None = Field(None, max_length=80)
    model: str | None = Field(None, max_length=80)
    model_year: int | None = Field(None, ge=1950, le=2100)
    notes: str | None = None
    initial_spec: VehicleSpecVersionFields | None = None


class VehiclePatchRequest(BaseModel):
    """PATCH /api/v1/vehicles/{id} — Update vehicle (Section 9.4).

    Note: asset_code is NOT patchable.
    """

    plate: str | None = Field(None, min_length=1, max_length=32)
    brand: str | None = Field(None, max_length=80)
    model: str | None = Field(None, max_length=80)
    model_year: int | None = Field(None, ge=1950, le=2100)
    ownership_type: str | None = Field(None, pattern=r"^(OWNED|LEASED|THIRD_PARTY)$")
    notes: str | None = None


class VehicleSpecVersionFields(BaseModel):
    """Shared spec fields for vehicle spec versions (Section 8.4 columns)."""

    change_reason: str = Field(..., min_length=1)
    effective_from_utc: datetime.datetime | None = None
    fuel_type: str | None = Field(None, pattern=r"^(DIESEL|LNG|CNG|ELECTRIC|HYBRID|OTHER)$")
    powertrain_type: str | None = Field(None, pattern=r"^(ICE|BEV|PHEV|HEV|FCEV|OTHER)$")
    engine_power_kw: Decimal | None = Field(None, gt=0)
    engine_displacement_l: Decimal | None = Field(None, gt=0)
    emission_class: str | None = Field(None, pattern=r"^(EURO_3|EURO_4|EURO_5|EURO_6|OTHER)$")
    transmission_type: str | None = Field(None, pattern=r"^(MANUAL|AUTOMATED_MANUAL|AUTOMATIC|OTHER)$")
    gear_count: int | None = Field(None, ge=1, le=24)
    final_drive_ratio: Decimal | None = Field(None, gt=0)
    axle_config: str | None = Field(None, pattern=r"^(4X2|6X2|6X4|8X2|8X4|OTHER)$")
    total_axle_count: int | None = Field(None, ge=1, le=6)
    driven_axle_count: int | None = Field(None, ge=1, le=4)
    curb_weight_kg: Decimal | None = Field(None, gt=0)
    gvwr_kg: Decimal | None = Field(None, gt=0)
    gcwr_kg: Decimal | None = Field(None, gt=0)
    payload_capacity_kg: Decimal | None = Field(None, ge=0)
    tractor_cab_type: str | None = Field(None, pattern=r"^(DAY|SLEEPER|OTHER)$")
    roof_height_class: str | None = Field(None, pattern=r"^(LOW|MEDIUM|HIGH|OTHER)$")
    aero_package_level: str | None = Field(None, pattern=r"^(NONE|LOW|MEDIUM|HIGH)$")
    tire_rr_class: str | None = Field(None, pattern=r"^(UNKNOWN|STANDARD|LOW_RR|ULTRA_LOW_RR)$")
    tire_type: str | None = Field(None, pattern=r"^(STANDARD|WIDE_BASE|OTHER)$")
    speed_limiter_kph: int | None = Field(None, ge=20, le=180)
    pto_present: bool | None = None
    apu_present: bool | None = None
    idle_reduction_type: str | None = Field(None, pattern=r"^(NONE|APU|BATTERY_AC|AUTO_START_STOP|OTHER)$")
    first_registration_date: datetime.date | None = None
    in_service_date: datetime.date | None = None


class VehicleSpecVersionRequest(VehicleSpecVersionFields):
    """POST /api/v1/vehicles/{id}/spec-versions — Create vehicle spec version."""


# --- Trailer ---


class TrailerCreateRequest(BaseModel):
    """POST /api/v1/trailers — Create a trailer."""

    asset_code: str = Field(..., min_length=1, max_length=50)
    plate: str = Field(..., min_length=1, max_length=32)
    ownership_type: str = Field(..., pattern=r"^(OWNED|LEASED|THIRD_PARTY)$")
    brand: str | None = Field(None, max_length=80)
    model: str | None = Field(None, max_length=80)
    model_year: int | None = Field(None, ge=1950, le=2100)
    notes: str | None = None
    initial_spec: TrailerSpecVersionFields | None = None


class TrailerPatchRequest(BaseModel):
    """PATCH /api/v1/trailers/{id} — Update trailer."""

    plate: str | None = Field(None, min_length=1, max_length=32)
    brand: str | None = Field(None, max_length=80)
    model: str | None = Field(None, max_length=80)
    model_year: int | None = Field(None, ge=1950, le=2100)
    ownership_type: str | None = Field(None, pattern=r"^(OWNED|LEASED|THIRD_PARTY)$")
    notes: str | None = None


class TrailerSpecVersionFields(BaseModel):
    """Shared spec fields for trailer spec versions (Section 8.5 columns)."""

    change_reason: str = Field(..., min_length=1)
    effective_from_utc: datetime.datetime | None = None
    trailer_type: str | None = Field(
        None,
        pattern=r"^(DRY_VAN|REEFER|TANKER|FLATBED|CURTAIN|TIPPER|CONTAINER_CHASSIS|OTHER)$",
    )
    body_type: str | None = Field(None, pattern=r"^(BOX|TANK|OPEN|CURTAIN|OTHER)$")
    tare_weight_kg: Decimal | None = Field(None, gt=0)
    max_payload_kg: Decimal | None = Field(None, ge=0)
    axle_count: int | None = Field(None, ge=1, le=8)
    lift_axle_present: bool | None = None
    body_height_mm: int | None = Field(None, gt=0)
    body_length_mm: int | None = Field(None, gt=0)
    body_width_mm: int | None = Field(None, gt=0)
    tire_rr_class: str | None = Field(None, pattern=r"^(UNKNOWN|STANDARD|LOW_RR|ULTRA_LOW_RR)$")
    tire_type: str | None = Field(None, pattern=r"^(STANDARD|WIDE_BASE|OTHER)$")
    side_skirts_present: bool | None = None
    rear_tail_present: bool | None = None
    gap_reducer_present: bool | None = None
    wheel_covers_present: bool | None = None
    reefer_unit_present: bool | None = None
    reefer_unit_type: str | None = Field(None, pattern=r"^(DIESEL|ELECTRIC|HYBRID|OTHER)$")
    reefer_power_source: str | None = Field(None, pattern=r"^(SELF_POWERED|TRACTOR_POWERED|GRID_CHARGED|OTHER)$")
    aero_package_level: str | None = Field(None, pattern=r"^(NONE|LOW|MEDIUM|HIGH)$")


class TrailerSpecVersionRequest(TrailerSpecVersionFields):
    """POST /api/v1/trailers/{id}/spec-versions — Create trailer spec version."""


# --- Lifecycle ---


class LifecycleActionRequest(BaseModel):
    """POST deactivate/reactivate/soft-delete — reason is required (Gap #6)."""

    reason: str = Field(..., min_length=1)


class HardDeleteRequest(BaseModel):
    """POST hard-delete — reason is required."""

    reason: str = Field(..., min_length=1)


# --- Internal ---


class TripCompatRequest(BaseModel):
    """POST /internal/v1/trip-references/validate (Section 9)."""

    driver_id: str = Field(..., min_length=1)
    vehicle_id: str | None = Field(None, min_length=1)
    trailer_id: str | None = None


class FuelMetadataResolveRequest(BaseModel):
    """POST /internal/v1/assets/fuel-metadata/resolve."""

    vehicle_id: str = Field(..., min_length=1)
    trailer_id: str | None = None
    at: datetime.datetime | None = None


class ValidateBulkRequest(BaseModel):
    """POST /internal/v1/assets/validate-bulk."""

    vehicle_ids: list[str] | None = Field(None, max_length=100)
    trailer_ids: list[str] | None = Field(None, max_length=100)
