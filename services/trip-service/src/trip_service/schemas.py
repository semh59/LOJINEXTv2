"""Pydantic schemas for API request/response serialization."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from trip_service.timezones import parse_local_datetime, validate_timezone_name

NonEmptyStr = Annotated[str, Field(min_length=1)]
OptionalNonEmptyStr = NonEmptyStr | None
NonNegativeInt = Annotated[int, Field(ge=0)]


def _validate_timezone(value: str) -> str:
    return validate_timezone_name(value)


def _validate_local_datetime(value: str) -> str:
    parse_local_datetime(value)
    return value


def _validate_weight_triplet(tare: int | None, gross: int | None, net: int | None) -> None:
    if tare is None or gross is None or net is None:
        return
    if gross < tare:
        raise ValueError("gross_weight_kg must be greater than or equal to tare_weight_kg.")
    if net != gross - tare:
        raise ValueError("net_weight_kg must equal gross_weight_kg - tare_weight_kg.")


class EnrichmentSummary(BaseModel):
    """Enrichment sub-object embedded in Trip Resource."""

    enrichment_status: str
    route_status: str
    data_quality_flag: str


class EvidenceSummary(BaseModel):
    """Evidence summary sub-object embedded in Trip Resource."""

    normalized_truck_plate: str | None = None
    normalized_trailer_plate: str | None = None
    origin_name_raw: str | None = None
    destination_name_raw: str | None = None


class TripResource(BaseModel):
    """Full trip resource returned by most endpoints."""

    id: str
    trip_no: str
    source_type: str
    source_slip_no: str | None = None
    source_reference_key: str | None = None
    review_reason_code: str | None = None
    base_trip_id: str | None = None
    driver_id: str
    vehicle_id: str | None = None
    trailer_id: str | None = None
    route_pair_id: str | None = None
    route_id: str | None = None
    origin_location_id: str | None = None
    origin_name_snapshot: str | None = None
    destination_location_id: str | None = None
    destination_name_snapshot: str | None = None
    trip_datetime_utc: datetime
    trip_timezone: str
    planned_duration_s: int | None = None
    planned_end_utc: datetime | None = None
    tare_weight_kg: int | None = None
    gross_weight_kg: int | None = None
    net_weight_kg: int | None = None
    is_empty_return: bool
    status: str
    version: int
    enrichment: EnrichmentSummary | None = None
    evidence_summary: EvidenceSummary | None = None
    created_at_utc: datetime
    updated_at_utc: datetime
    soft_deleted_at_utc: datetime | None = None

    model_config = {"from_attributes": True}


class PaginationMeta(BaseModel):
    """Pagination metadata returned in list responses."""

    page: int
    per_page: int
    total_items: int
    total_pages: int
    sort: str


class TripListResponse(BaseModel):
    """List response with items + meta."""

    items: list[TripResource]
    meta: PaginationMeta


class ManualCreateRequest(BaseModel):
    """Admin manual trip creation."""

    trip_no: NonEmptyStr
    route_pair_id: NonEmptyStr
    trip_start_local: str
    trip_timezone: NonEmptyStr = "Europe/Istanbul"
    driver_id: NonEmptyStr
    vehicle_id: NonEmptyStr
    trailer_id: OptionalNonEmptyStr = None
    tare_weight_kg: NonNegativeInt
    gross_weight_kg: NonNegativeInt
    net_weight_kg: NonNegativeInt
    note: str | None = None
    is_empty_return: bool | None = Field(default=None, exclude=True)

    @field_validator("is_empty_return", mode="before")
    @classmethod
    def reject_is_empty_return(cls, value: Any) -> None:
        if value is not None:
            raise ValueError("is_empty_return is not allowed in manual create. Use the empty-return endpoint.")
        return None

    @field_validator("trip_start_local")
    @classmethod
    def validate_trip_start_local(cls, value: str) -> str:
        return _validate_local_datetime(value)

    @field_validator("trip_timezone")
    @classmethod
    def validate_trip_timezone(cls, value: str) -> str:
        return _validate_timezone(value)

    @model_validator(mode="after")
    def validate_weights(self) -> "ManualCreateRequest":
        _validate_weight_triplet(self.tare_weight_kg, self.gross_weight_kg, self.net_weight_kg)
        return self


class EditTripRequest(BaseModel):
    """Editable fields for PATCH."""

    route_pair_id: OptionalNonEmptyStr = None
    trip_start_local: str | None = None
    trip_timezone: str | None = None
    driver_id: OptionalNonEmptyStr = None
    vehicle_id: OptionalNonEmptyStr = None
    trailer_id: OptionalNonEmptyStr = None
    tare_weight_kg: Annotated[int | None, Field(default=None, ge=0)] = None
    gross_weight_kg: Annotated[int | None, Field(default=None, ge=0)] = None
    net_weight_kg: Annotated[int | None, Field(default=None, ge=0)] = None
    note: str | None = None
    change_reason: str | None = None

    @field_validator("trip_start_local")
    @classmethod
    def validate_trip_start_local(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _validate_local_datetime(value)

    @field_validator("trip_timezone")
    @classmethod
    def validate_trip_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _validate_timezone(value)

    @model_validator(mode="after")
    def validate_timezone_patch(self) -> "EditTripRequest":
        if self.trip_timezone is not None and self.trip_start_local is None:
            raise ValueError("trip_timezone cannot be updated without trip_start_local.")
        return self

    @model_validator(mode="after")
    def validate_weight_triplet_patch(self) -> "EditTripRequest":
        _validate_weight_triplet(self.tare_weight_kg, self.gross_weight_kg, self.net_weight_kg)
        return self


class ApproveRequest(BaseModel):
    """Approve a pending trip."""

    note: str | None = None


class RejectRequest(BaseModel):
    """Reject a pending trip."""

    reason: str | None = None


class HardDeleteRequest(BaseModel):
    """Hard-delete request body."""

    reason: NonEmptyStr


class EmptyReturnRequest(BaseModel):
    """Create empty-return trip."""

    trip_start_local: str
    trip_timezone: NonEmptyStr = "Europe/Istanbul"
    driver_id: NonEmptyStr
    vehicle_id: NonEmptyStr
    trailer_id: OptionalNonEmptyStr = None
    tare_weight_kg: NonNegativeInt
    gross_weight_kg: NonNegativeInt
    net_weight_kg: NonNegativeInt
    note: str | None = None

    @field_validator("trip_start_local")
    @classmethod
    def validate_trip_start_local(cls, value: str) -> str:
        return _validate_local_datetime(value)

    @field_validator("trip_timezone")
    @classmethod
    def validate_trip_timezone(cls, value: str) -> str:
        return _validate_timezone(value)

    @model_validator(mode="after")
    def validate_weights(self) -> "EmptyReturnRequest":
        _validate_weight_triplet(self.tare_weight_kg, self.gross_weight_kg, self.net_weight_kg)
        return self


class TelegramSlipIngestRequest(BaseModel):
    """Normalized Telegram slip payload for full ingest."""

    source_type: Literal["TELEGRAM_TRIP_SLIP"] = "TELEGRAM_TRIP_SLIP"
    source_slip_no: NonEmptyStr
    source_reference_key: NonEmptyStr
    driver_id: NonEmptyStr
    vehicle_id: NonEmptyStr
    trailer_id: OptionalNonEmptyStr = None
    origin_name: NonEmptyStr
    destination_name: NonEmptyStr
    trip_start_local: str
    trip_timezone: NonEmptyStr = "Europe/Istanbul"
    tare_weight_kg: NonNegativeInt
    gross_weight_kg: NonNegativeInt
    net_weight_kg: NonNegativeInt
    file_key: str | None = None
    raw_text_ref: str | None = None
    ocr_confidence: float | None = None
    normalized_truck_plate: str | None = None
    normalized_trailer_plate: str | None = None

    @field_validator("trip_start_local")
    @classmethod
    def validate_trip_start_local(cls, value: str) -> str:
        return _validate_local_datetime(value)

    @field_validator("trip_timezone")
    @classmethod
    def validate_trip_timezone(cls, value: str) -> str:
        return _validate_timezone(value)

    @model_validator(mode="after")
    def validate_weights(self) -> "TelegramSlipIngestRequest":
        _validate_weight_triplet(self.tare_weight_kg, self.gross_weight_kg, self.net_weight_kg)
        return self


class TelegramFallbackIngestRequest(BaseModel):
    """Fallback Telegram ingest payload when parsing fails."""

    source_reference_key: NonEmptyStr
    driver_id: NonEmptyStr
    message_sent_at_utc: datetime
    file_key: str | None = None
    raw_text_ref: str | None = None
    fallback_reason: NonEmptyStr

    @field_validator("message_sent_at_utc")
    @classmethod
    def validate_message_sent_at_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("message_sent_at_utc must include timezone information.")
        return value


class ExcelIngestRequest(BaseModel):
    """Structured Excel-service ingest payload."""

    source_type: Literal["EXCEL_IMPORT"] = "EXCEL_IMPORT"
    source_reference_key: NonEmptyStr
    trip_no: NonEmptyStr
    route_pair_id: NonEmptyStr
    trip_start_local: str
    trip_timezone: NonEmptyStr = "Europe/Istanbul"
    driver_id: NonEmptyStr
    vehicle_id: NonEmptyStr
    trailer_id: OptionalNonEmptyStr = None
    tare_weight_kg: NonNegativeInt
    gross_weight_kg: NonNegativeInt
    net_weight_kg: NonNegativeInt
    row_number: Annotated[int | None, Field(default=None, ge=1)] = None
    note: str | None = None

    @field_validator("trip_start_local")
    @classmethod
    def validate_trip_start_local(cls, value: str) -> str:
        return _validate_local_datetime(value)

    @field_validator("trip_timezone")
    @classmethod
    def validate_trip_timezone(cls, value: str) -> str:
        return _validate_timezone(value)

    @model_validator(mode="after")
    def validate_weights(self) -> "ExcelIngestRequest":
        _validate_weight_triplet(self.tare_weight_kg, self.gross_weight_kg, self.net_weight_kg)
        return self


class AssetReferenceCheckRequest(BaseModel):
    """Generic internal request for active asset reference checks."""

    asset_type: Literal["DRIVER", "VEHICLE", "TRAILER"]
    asset_id: NonEmptyStr


class AssetReferenceCheckResponse(BaseModel):
    """Internal response for active asset reference checks."""

    asset_type: str
    asset_id: str
    is_referenced: bool
    active_trip_count: int


class TimelineItem(BaseModel):
    """Timeline item resource."""

    id: str
    event_type: str
    actor_type: str
    actor_id: str
    note: str | None = None
    payload_json: Any | None = None
    created_at_utc: datetime

    model_config = {"from_attributes": True}


class TimelineResponse(BaseModel):
    """Timeline response."""

    items: list[TimelineItem]


class DriverStatementRow(BaseModel):
    """Driver statement row."""

    date: str
    truck_plate: str
    from_: str = Field(alias="from")
    to: str
    net_weight_kg: int
    hour: str
    fee: str = ""
    approval: str = ""

    model_config = {"populate_by_name": True}


class DriverStatementResponse(BaseModel):
    """Driver statement list response."""

    items: list[DriverStatementRow]
    meta: PaginationMeta


class RetryEnrichmentResponse(BaseModel):
    """Retry enrichment response."""

    trip_id: str
    queued: bool
