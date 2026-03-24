"""Pydantic schemas for API request/response serialization.

Implements V8 Section 9 — Shared Resource Schemas and endpoint contracts.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# V8 Section 9.1 — Trip Resource (response)
# ---------------------------------------------------------------------------


class EnrichmentSummary(BaseModel):
    """Enrichment sub-object embedded in Trip Resource."""

    enrichment_status: str
    route_status: str
    weather_status: str
    data_quality_flag: str


class EvidenceSummary(BaseModel):
    """Evidence summary sub-object embedded in Trip Resource."""

    normalized_truck_plate: str | None = None
    normalized_trailer_plate: str | None = None
    origin_name_raw: str | None = None
    destination_name_raw: str | None = None


class TripResource(BaseModel):
    """V8 Section 9.1 — Full trip resource returned by most endpoints."""

    id: str
    trip_no: str
    source_type: str
    source_slip_no: str | None = None
    base_trip_id: str | None = None
    driver_id: str
    vehicle_id: str | None = None
    trailer_id: str | None = None
    route_id: str | None = None
    trip_datetime_utc: datetime
    trip_timezone: str
    tare_weight_kg: int
    gross_weight_kg: int
    net_weight_kg: int
    is_empty_return: bool
    status: str
    version: int
    enrichment: EnrichmentSummary | None = None
    evidence_summary: EvidenceSummary | None = None
    created_at_utc: datetime
    updated_at_utc: datetime
    soft_deleted_at_utc: datetime | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# V8 Section 9.2 — Trip List Response
# ---------------------------------------------------------------------------


class PaginationMeta(BaseModel):
    """Pagination metadata returned in list responses."""

    page: int
    per_page: int
    total_items: int
    total_pages: int
    sort: str


class TripListResponse(BaseModel):
    """V8 Section 9.2 — List response with items + meta."""

    items: list[TripResource]
    meta: PaginationMeta


# ---------------------------------------------------------------------------
# V8 Section 10.1 — Ingest Slip Request
# ---------------------------------------------------------------------------


class IngestSlipRequest(BaseModel):
    """V8 Section 10.1 — Normalized trip slip payload from Slip Processing Service."""

    source_type: str = "TELEGRAM_TRIP_SLIP"
    source_slip_no: str
    driver_id: str
    vehicle_id: str | None = None
    trailer_id: str | None = None
    origin_name: str
    destination_name: str
    trip_datetime_local: str  # ISO 8601 without timezone
    trip_timezone: str = "Europe/Istanbul"
    tare_weight_kg: int
    gross_weight_kg: int
    net_weight_kg: int
    file_key: str | None = None
    raw_text_ref: str | None = None
    ocr_confidence: float | None = None
    normalized_truck_plate: str | None = None
    normalized_trailer_plate: str | None = None


# ---------------------------------------------------------------------------
# V8 Section 10.2 — Manual Create Request
# ---------------------------------------------------------------------------


class ManualCreateRequest(BaseModel):
    """V8 Section 10.2 — Admin manual trip creation."""

    trip_no: str
    driver_id: str
    vehicle_id: str | None = None
    trailer_id: str | None = None
    route_id: str
    trip_datetime_local: str
    trip_timezone: str = "Europe/Istanbul"
    tare_weight_kg: int
    gross_weight_kg: int
    net_weight_kg: int
    note: str | None = None

    # V8 Section 10.2: is_empty_return MUST NOT be accepted. Reject with 422.
    is_empty_return: bool | None = Field(default=None, exclude=True)

    @field_validator("is_empty_return", mode="before")
    @classmethod
    def reject_is_empty_return(cls, v: Any) -> None:
        """V8: If is_empty_return is provided in request body, reject with 422."""
        if v is not None:
            raise ValueError("is_empty_return is not allowed in manual create. Use the empty-return endpoint.")
        return None


# ---------------------------------------------------------------------------
# V8 Section 10.6 — Edit Trip Request
# ---------------------------------------------------------------------------


class EditTripRequest(BaseModel):
    """V8 Section 10.6 — Editable fields for PATCH."""

    driver_id: str | None = None
    vehicle_id: str | None = None
    trailer_id: str | None = None
    route_id: str | None = None
    trip_datetime_local: str | None = None
    trip_timezone: str | None = None
    tare_weight_kg: int | None = None
    gross_weight_kg: int | None = None
    net_weight_kg: int | None = None


# ---------------------------------------------------------------------------
# V8 Section 10.7 — Approve Request
# ---------------------------------------------------------------------------


class ApproveRequest(BaseModel):
    """V8 Section 10.7 — Approve pending trip."""

    note: str | None = None


# ---------------------------------------------------------------------------
# V8 Section 10.8 — Empty Return Request
# ---------------------------------------------------------------------------


class EmptyReturnRequest(BaseModel):
    """V8 Section 10.8 — Create empty-return trip."""

    driver_id: str
    vehicle_id: str | None = None
    trailer_id: str | None = None
    route_id: str | None = None
    trip_datetime_local: str
    trip_timezone: str = "Europe/Istanbul"
    tare_weight_kg: int
    gross_weight_kg: int
    net_weight_kg: int
    note: str | None = None


# ---------------------------------------------------------------------------
# V8 Section 10.13 — Import Job Request
# ---------------------------------------------------------------------------


class CreateImportJobRequest(BaseModel):
    """V8 Section 10.13 — Create import job."""

    file_key: str
    import_mode: str = "PARTIAL"
    skip_weather_enrichment: bool = False


# ---------------------------------------------------------------------------
# V8 Section 9.3 — Import Job Resource
# ---------------------------------------------------------------------------


class ImportJobResource(BaseModel):
    """V8 Section 9.3."""

    id: str
    file_key: str
    status: str
    import_mode: str
    skip_weather_enrichment: bool
    imported_count: int
    rejected_count: int
    enrichment_pending_count: int
    enrichment_failed_count: int
    error_summary_json: Any | None = None
    created_at_utc: datetime
    updated_at_utc: datetime
    completed_at_utc: datetime | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# V8 Section 10.15 — Export Job Request
# ---------------------------------------------------------------------------


class ExportFilters(BaseModel):
    """Filters for export job creation."""

    driver_id: str | None = None
    vehicle_id: str | None = None
    route_id: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    timezone: str = "Europe/Istanbul"
    include_soft_deleted: bool = False


class CreateExportJobRequest(BaseModel):
    """V8 Section 10.15."""

    filters: ExportFilters


# ---------------------------------------------------------------------------
# V8 Section 9.4 — Export Job Resource
# ---------------------------------------------------------------------------


class ExportJobResource(BaseModel):
    """V8 Section 9.4."""

    id: str
    status: str
    requested_filters_json: Any
    result_file_key: str | None = None
    result_file_expires_at_utc: datetime | None = None
    created_at_utc: datetime
    updated_at_utc: datetime
    completed_at_utc: datetime | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# V8 Section 9.5 — Timeline Item
# ---------------------------------------------------------------------------


class TimelineItem(BaseModel):
    """V8 Section 9.5."""

    id: str
    event_type: str
    actor_type: str
    actor_id: str
    note: str | None = None
    payload_json: Any | None = None
    created_at_utc: datetime

    model_config = {"from_attributes": True}


class TimelineResponse(BaseModel):
    """V8 Section 10.5 — timeline returns all items, no pagination."""

    items: list[TimelineItem]


# ---------------------------------------------------------------------------
# V8 Section 9.6 — Driver Statement Row
# ---------------------------------------------------------------------------


class DriverStatementRow(BaseModel):
    """V8 Section 9.6 — V8 renamed tonnage → net_weight_kg."""

    date: str  # YYYY-MM-DD
    truck_plate: str
    from_: str = Field(alias="from")  # 'from' is Python keyword
    to: str
    net_weight_kg: int
    hour: str  # HH:mm
    fee: str = ""  # always empty in V1
    approval: str = ""  # always empty in V1

    model_config = {"populate_by_name": True}


class DriverStatementResponse(BaseModel):
    """V8 Section 10.11 — Driver statement list response."""

    items: list[DriverStatementRow]
    meta: PaginationMeta


# ---------------------------------------------------------------------------
# V8 Section 10.12 — File Upload Response
# ---------------------------------------------------------------------------


class FileUploadResponse(BaseModel):
    """V8 Section 10.12."""

    file_key: str


# ---------------------------------------------------------------------------
# V8 Section 10.18 — Retry Enrichment Response
# ---------------------------------------------------------------------------


class RetryEnrichmentResponse(BaseModel):
    """V8 Section 10.18."""

    trip_id: str
    queued: bool
