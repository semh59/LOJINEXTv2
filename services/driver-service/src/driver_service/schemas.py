"""Pydantic schemas for Driver Service request/response contracts (spec Section 3)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Create driver (§3.1)
# ---------------------------------------------------------------------------


class CreateDriverRequest(BaseModel):
    """Request body for POST /api/v1/drivers."""

    company_driver_code: str | None = Field(None, max_length=64)
    full_name: str = Field(..., min_length=2, max_length=255)
    phone: str = Field(..., min_length=1)
    telegram_user_id: str | None = Field(None, max_length=64)
    license_class: str = Field(..., min_length=1, max_length=32)
    employment_start_date: date
    note: str | None = Field(None, max_length=2000)


# ---------------------------------------------------------------------------
# Update driver (§3.4)
# ---------------------------------------------------------------------------


class PatchDriverRequest(BaseModel):
    """Request body for PATCH /api/v1/drivers/{driver_id}. All fields optional."""

    company_driver_code: str | None = Field(None, max_length=64)
    full_name: str | None = Field(None, min_length=2, max_length=255)
    phone: str | None = Field(None, min_length=1)
    telegram_user_id: str | None = Field(None, max_length=64)
    license_class: str | None = Field(None, min_length=1, max_length=32)
    employment_start_date: date | None = None
    employment_end_date: date | None = None
    note: str | None = Field(None, max_length=2000)


# ---------------------------------------------------------------------------
# Inactivate (§3.5)
# ---------------------------------------------------------------------------


class InactivateDriverRequest(BaseModel):
    """Request body for POST /api/v1/drivers/{driver_id}/inactivate."""

    inactive_reason: str = Field(..., min_length=1, max_length=255)
    employment_end_date: date | None = None


# ---------------------------------------------------------------------------
# Soft delete (§3.7)
# ---------------------------------------------------------------------------


class SoftDeleteDriverRequest(BaseModel):
    """Request body for POST /api/v1/drivers/{driver_id}/soft-delete."""

    reason: str = Field(..., min_length=1, max_length=255)


# ---------------------------------------------------------------------------
# Eligibility check (§3.11)
# ---------------------------------------------------------------------------


class EligibilityCheckRequest(BaseModel):
    """Request body for POST /internal/v1/drivers/eligibility/check."""

    driver_ids: list[str] = Field(..., max_length=200)


class EligibilityItem(BaseModel):
    """Single item in the eligibility check response."""

    driver_id: str
    exists: bool
    status: str | None = None
    lifecycle_state: str | None = None
    has_telegram: bool = False
    is_assignable: bool = False


# ---------------------------------------------------------------------------
# Merge (§3.15)
# ---------------------------------------------------------------------------


class MergeDriversRequest(BaseModel):
    """Request body for POST /internal/v1/drivers/merge."""

    source_driver_id: str
    target_driver_id: str
    reason: str = Field(..., min_length=1, max_length=255)


# ---------------------------------------------------------------------------
# Driver resource response shapes
# ---------------------------------------------------------------------------


class DriverAdminResponse(BaseModel):
    """Full driver resource shape for ADMIN callers."""

    driver_id: str
    company_driver_code: str | None = None
    full_name: str
    phone: str | None = None
    phone_normalization_status: str
    telegram_user_id: str | None = None
    license_class: str
    employment_start_date: date
    employment_end_date: date | None = None
    status: str
    lifecycle_state: str
    inactive_reason: str | None = None
    is_assignable: bool
    note: str | None = None
    row_version: int
    created_at_utc: datetime
    updated_at_utc: datetime
    soft_deleted_at_utc: datetime | None = None
    soft_delete_reason: str | None = None


class DriverManagerResponse(BaseModel):
    """Driver resource shape for MANAGER callers — phone masked, note omitted."""

    driver_id: str
    company_driver_code: str | None = None
    full_name: str
    phone: str | None = None
    telegram_user_id: str | None = None
    license_class: str
    employment_start_date: date
    employment_end_date: date | None = None
    status: str
    lifecycle_state: str
    is_assignable: bool
    row_version: int
    updated_at_utc: datetime


class DriverInternalResponse(BaseModel):
    """Driver resource shape for SERVICE callers — minimal fields."""

    driver_id: str
    company_driver_code: str | None = None
    full_name: str
    telegram_user_id: str | None = None
    license_class: str
    status: str
    lifecycle_state: str
    is_assignable: bool


# ---------------------------------------------------------------------------
# Paginated list response
# ---------------------------------------------------------------------------


class PaginatedDriverResponse(BaseModel):
    """Paged list of driver resources."""

    page: int
    per_page: int
    total: int
    items: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


class AuditLogEntry(BaseModel):
    """Single audit log entry in the response."""

    audit_id: str
    driver_id: str
    action_type: str
    changed_fields_json: str | None = None
    actor_id: str
    actor_role: str
    reason: str | None = None
    request_id: str | None = None
    created_at_utc: datetime


class PaginatedAuditResponse(BaseModel):
    """Paged list of audit log entries."""

    page: int
    per_page: int
    total: int
    items: list[AuditLogEntry]


# ---------------------------------------------------------------------------
# Import jobs (§3.12, §3.13)
# ---------------------------------------------------------------------------


class ImportRowInput(BaseModel):
    """Single row in an import request."""

    company_driver_code: str = Field(..., min_length=1, max_length=64)
    full_name: str = Field(..., min_length=2, max_length=255)
    phone: str | None = None
    telegram_user_id: str | None = Field(None, max_length=64)
    license_class: str = Field(..., min_length=1, max_length=32)
    employment_start_date: date
    employment_end_date: date | None = None
    status: str = Field(..., pattern="^(ACTIVE|INACTIVE)$")
    inactive_reason: str | None = Field(None, max_length=255)
    note: str | None = Field(None, max_length=2000)


class CreateImportJobRequest(BaseModel):
    """Request body for POST /internal/v1/driver-import-jobs."""

    strict_mode: bool = False
    rows: list[ImportRowInput]


class ImportJobResponse(BaseModel):
    """Import job summary response."""

    import_job_id: str
    status: str
    total_rows: int
    success_rows: int
    failed_rows: int
    created_at_utc: datetime
    started_at_utc: datetime | None = None
    completed_at_utc: datetime | None = None
