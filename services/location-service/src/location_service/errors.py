"""Shared error handling following v0.7 Section 7 — Problem Details Contract.

All non-2xx responses use application/problem+json with stable extension fields.
"""

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class ProblemDetailError(Exception):
    """Raise from any handler to return a structured problem+json error.

    All error codes follow the LOCATION_ prefix convention from Section 7.
    """

    def __init__(
        self,
        status: int,
        code: str,
        title: str,
        detail: str,
        instance: str = "",
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.instance = instance
        self.errors = errors or []
        super().__init__(detail)


async def problem_detail_handler(request: Request, exc: Exception) -> JSONResponse:
    """Convert ProblemDetail exceptions into RFC 9457 problem+json responses."""
    if not isinstance(exc, ProblemDetailError):
        # Fallback for unexpected exceptions if registered as handler
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

    request_id = getattr(request.state, "request_id", "unknown")
    body: dict[str, Any] = {
        "type": f"https://location-service/errors/{exc.code}",
        "title": exc.title,
        "status": exc.status,
        "detail": exc.detail,
        "instance": exc.instance or str(request.url.path),
        "code": exc.code,
        "request_id": request_id,
    }
    if exc.errors:
        body["errors"] = exc.errors
    return JSONResponse(status_code=exc.status, content=body, media_type="application/problem+json")


# ---------------------------------------------------------------------------
# Point errors (Section 7.1–7.4)
# ---------------------------------------------------------------------------


def point_not_found(location_id: str) -> ProblemDetailError:
    """Section 7.3: LOCATION_POINT_NOT_FOUND."""
    return ProblemDetailError(404, "LOCATION_POINT_NOT_FOUND", "Point not found", f"Point {location_id} not found.")


def point_code_conflict(code: str) -> ProblemDetailError:
    """Section 7.1: LOCATION_POINT_CODE_CONFLICT."""
    return ProblemDetailError(409, "LOCATION_POINT_CODE_CONFLICT", "Conflict", f"Point code '{code}' already exists.")


def point_name_conflict(detail: str = "") -> ProblemDetailError:
    """Section 7.1: LOCATION_POINT_NAME_CONFLICT."""
    return ProblemDetailError(
        409, "LOCATION_POINT_NAME_CONFLICT", "Conflict", detail or "Normalized name conflicts with existing point."
    )


def point_coordinate_conflict() -> ProblemDetailError:
    """Section 7.1: LOCATION_POINT_COORDINATE_CONFLICT."""
    return ProblemDetailError(
        409, "LOCATION_POINT_COORDINATE_CONFLICT", "Conflict", "Coordinates conflict with existing point."
    )


def point_invalid_coordinates(detail: str = "") -> ProblemDetailError:
    """Section 7.1: LOCATION_POINT_INVALID_COORDINATES."""
    return ProblemDetailError(
        422,
        "LOCATION_POINT_INVALID_COORDINATES",
        "Invalid coordinates",
        detail or "Coordinates out of range or null island.",
    )


def point_name_blank() -> ProblemDetailError:
    """Section 7.1: LOCATION_POINT_NAME_BLANK."""
    return ProblemDetailError(422, "LOCATION_POINT_NAME_BLANK", "Validation error", "Point name must not be blank.")


def point_immutable_field_modification() -> ProblemDetailError:
    """Section 7.4: LOCATION_POINT_IMMUTABLE_FIELD_MODIFICATION."""
    return ProblemDetailError(
        422,
        "LOCATION_POINT_IMMUTABLE_FIELD_MODIFICATION",
        "Immutable field",
        "Cannot modify immutable fields: location_id, code, latitude, longitude, normalized_name_*.",
    )


def point_in_use_by_active_pair() -> ProblemDetailError:
    """Section 7.4 / BR-11: LOCATION_POINT_IN_USE_BY_ACTIVE_PAIR."""
    return ProblemDetailError(
        409,
        "LOCATION_POINT_IN_USE_BY_ACTIVE_PAIR",
        "Conflict",
        "Point is referenced by an ACTIVE or DRAFT pair; cannot deactivate.",
    )


def point_version_mismatch() -> ProblemDetailError:
    """Section 7.4: LOCATION_POINT_VERSION_MISMATCH."""
    return ProblemDetailError(412, "LOCATION_POINT_VERSION_MISMATCH", "Precondition failed", "ETag does not match.")


def if_match_required() -> ProblemDetailError:
    """Section 7.4: LOCATION_IF_MATCH_REQUIRED."""
    return ProblemDetailError(428, "LOCATION_IF_MATCH_REQUIRED", "Precondition required", "If-Match header required.")


# ---------------------------------------------------------------------------
# Route pair errors (Section 7.5–7.7)
# ---------------------------------------------------------------------------


def route_pair_not_found(pair_id: str = "") -> ProblemDetailError:
    """Section 7.7: LOCATION_ROUTE_PAIR_NOT_FOUND."""
    return ProblemDetailError(
        404,
        "LOCATION_ROUTE_PAIR_NOT_FOUND",
        "Not found",
        f"Route pair {pair_id} not found." if pair_id else "Route pair not found.",
    )


def route_pair_already_exists_active() -> ProblemDetailError:
    """Section 7.5: LOCATION_ROUTE_PAIR_ALREADY_EXISTS_ACTIVE."""
    return ProblemDetailError(
        409,
        "LOCATION_ROUTE_PAIR_ALREADY_EXISTS_ACTIVE",
        "Conflict",
        "A route pair already exists for this origin/destination/profile (ACTIVE or DRAFT).",
    )


def route_pair_already_exists_deleted() -> ProblemDetailError:
    """Section 7.5: LOCATION_ROUTE_PAIR_ALREADY_EXISTS_DELETED."""
    return ProblemDetailError(
        409,
        "LOCATION_ROUTE_PAIR_ALREADY_EXISTS_DELETED",
        "Conflict",
        "A soft-deleted pair exists for this origin/destination/profile. Restore is not available in V1.",
    )


def route_origin_equals_destination() -> ProblemDetailError:
    """Section 7.5 / BR-01: LOCATION_ROUTE_ORIGIN_EQUALS_DESTINATION."""
    return ProblemDetailError(
        422,
        "LOCATION_ROUTE_ORIGIN_EQUALS_DESTINATION",
        "Validation error",
        "Origin and destination must be different points.",
    )


def point_inactive_for_new_pair() -> ProblemDetailError:
    """Section 7.5: LOCATION_POINT_INACTIVE_FOR_NEW_PAIR."""
    return ProblemDetailError(
        409, "LOCATION_POINT_INACTIVE_FOR_NEW_PAIR", "Conflict", "Cannot create pair with inactive point."
    )


def route_pair_version_mismatch() -> ProblemDetailError:
    """Section 7.9+: LOCATION_ROUTE_PAIR_VERSION_MISMATCH."""
    return ProblemDetailError(412, "LOCATION_ROUTE_PAIR_VERSION_MISMATCH", "Precondition failed", "ETag mismatch.")


# ---------------------------------------------------------------------------
# Processing / calculate / refresh errors (Sections 7.8–7.10A)
# ---------------------------------------------------------------------------


def route_pair_already_running() -> ProblemDetailError:
    """Section 7.8 / BR-04: LOCATION_ROUTE_PAIR_ALREADY_RUNNING."""
    return ProblemDetailError(409, "LOCATION_ROUTE_PAIR_ALREADY_RUNNING", "Conflict", "A run is already active.")


def route_pair_pending_draft_exists() -> ProblemDetailError:
    """Section 7.8 / BR-03: LOCATION_ROUTE_PAIR_PENDING_DRAFT_EXISTS."""
    return ProblemDetailError(409, "LOCATION_ROUTE_PAIR_PENDING_DRAFT_EXISTS", "Conflict", "Pending draft exists.")


def route_pair_soft_deleted() -> ProblemDetailError:
    """Section 7.8: LOCATION_ROUTE_PAIR_SOFT_DELETED."""
    return ProblemDetailError(409, "LOCATION_ROUTE_PAIR_SOFT_DELETED", "Conflict", "Pair is soft-deleted.")


def route_pair_already_active_use_refresh() -> ProblemDetailError:
    """Section 7.8: LOCATION_ROUTE_PAIR_ALREADY_ACTIVE_USE_REFRESH."""
    return ProblemDetailError(
        409, "LOCATION_ROUTE_PAIR_ALREADY_ACTIVE_USE_REFRESH", "Conflict", "Already active — use refresh instead."
    )


def route_pair_not_active_use_calculate() -> ProblemDetailError:
    """Section 7.9: LOCATION_ROUTE_PAIR_NOT_ACTIVE_USE_CALCULATE."""
    return ProblemDetailError(
        409, "LOCATION_ROUTE_PAIR_NOT_ACTIVE_USE_CALCULATE", "Conflict", "Not yet active — use calculate instead."
    )


def processing_run_not_found(run_id: str = "") -> ProblemDetailError:
    """Section 7.10: LOCATION_PROCESSING_RUN_NOT_FOUND."""
    return ProblemDetailError(404, "LOCATION_PROCESSING_RUN_NOT_FOUND", "Not found", "Processing run not found.")


def run_not_stuck() -> ProblemDetailError:
    """Section 7.10A: LOCATION_RUN_NOT_STUCK."""
    return ProblemDetailError(409, "LOCATION_RUN_NOT_STUCK", "Conflict", "Run is not stuck (SLA not reached).")


# ---------------------------------------------------------------------------
# Approval / draft errors (Sections 7.11, 7.14–7.15)
# ---------------------------------------------------------------------------


def route_pair_pending_draft_not_found() -> ProblemDetailError:
    """Section 7.11: LOCATION_ROUTE_PAIR_PENDING_DRAFT_NOT_FOUND."""
    return ProblemDetailError(404, "LOCATION_ROUTE_PAIR_PENDING_DRAFT_NOT_FOUND", "Not found", "No pending draft.")


def route_pair_draft_run_mismatch() -> ProblemDetailError:
    """Section 7.11: LOCATION_ROUTE_PAIR_DRAFT_RUN_MISMATCH."""
    return ProblemDetailError(409, "LOCATION_ROUTE_PAIR_DRAFT_RUN_MISMATCH", "Conflict", "Run ID does not match.")


def route_pair_not_ready_for_approval() -> ProblemDetailError:
    """Section 7.14: LOCATION_ROUTE_PAIR_NOT_READY_FOR_APPROVAL."""
    return ProblemDetailError(409, "LOCATION_ROUTE_PAIR_NOT_READY_FOR_APPROVAL", "Conflict", "No pending draft.")


def route_pair_version_conflict() -> ProblemDetailError:
    """Section 7.14: LOCATION_ROUTE_PAIR_VERSION_CONFLICT."""
    return ProblemDetailError(
        409, "LOCATION_ROUTE_PAIR_VERSION_CONFLICT", "Conflict", "Version numbers do not match pending draft."
    )


def version_segment_count_mismatch() -> ProblemDetailError:
    """Section 7.14: LOCATION_VERSION_SEGMENT_COUNT_MISMATCH."""
    return ProblemDetailError(
        409, "LOCATION_VERSION_SEGMENT_COUNT_MISMATCH", "Conflict", "Segment count in DB does not match version row."
    )


def route_pair_approve_run_mismatch() -> ProblemDetailError:
    """Section 7.14: LOCATION_ROUTE_PAIR_APPROVE_RUN_MISMATCH."""
    return ProblemDetailError(422, "LOCATION_ROUTE_PAIR_APPROVE_RUN_MISMATCH", "Validation error", "Run mismatch.")


def route_pair_draft_hash_mismatch() -> ProblemDetailError:
    """Section 7.14: LOCATION_ROUTE_PAIR_DRAFT_HASH_MISMATCH."""
    return ProblemDetailError(422, "LOCATION_ROUTE_PAIR_DRAFT_HASH_MISMATCH", "Validation error", "Hash mismatch.")


def route_pair_no_pending_draft() -> ProblemDetailError:
    """Section 7.15: LOCATION_ROUTE_PAIR_NO_PENDING_DRAFT."""
    return ProblemDetailError(409, "LOCATION_ROUTE_PAIR_NO_PENDING_DRAFT", "Conflict", "No pending draft to discard.")


def route_pair_run_in_progress() -> ProblemDetailError:
    """Section 7.15: LOCATION_ROUTE_PAIR_RUN_IN_PROGRESS."""
    return ProblemDetailError(409, "LOCATION_ROUTE_PAIR_RUN_IN_PROGRESS", "Conflict", "Run is still in progress.")


def route_pair_discard_run_mismatch() -> ProblemDetailError:
    """Section 7.15: LOCATION_ROUTE_PAIR_DISCARD_RUN_MISMATCH."""
    return ProblemDetailError(422, "LOCATION_ROUTE_PAIR_DISCARD_RUN_MISMATCH", "Validation error", "Run mismatch.")


# ---------------------------------------------------------------------------
# Delete errors (Sections 7.16–7.17)
# ---------------------------------------------------------------------------


def route_pair_already_soft_deleted() -> ProblemDetailError:
    """Section 7.16: LOCATION_ROUTE_PAIR_ALREADY_SOFT_DELETED."""
    return ProblemDetailError(409, "LOCATION_ROUTE_PAIR_ALREADY_SOFT_DELETED", "Conflict", "Already soft-deleted.")


def route_pair_not_soft_deleted() -> ProblemDetailError:
    """Section 7.17: LOCATION_ROUTE_PAIR_NOT_SOFT_DELETED."""
    return ProblemDetailError(409, "LOCATION_ROUTE_PAIR_NOT_SOFT_DELETED", "Conflict", "Pair is not soft-deleted.")


def route_pair_hard_delete_blocked_was_active() -> ProblemDetailError:
    """Section 7.17 / BR-07: LOCATION_ROUTE_PAIR_HARD_DELETE_BLOCKED_WAS_ACTIVE."""
    return ProblemDetailError(
        409,
        "LOCATION_ROUTE_PAIR_HARD_DELETE_BLOCKED_WAS_ACTIVE",
        "Conflict",
        "Pair has activation history; hard delete blocked.",
    )


def route_pair_hard_delete_grace_period_not_reached() -> ProblemDetailError:
    """Section 7.17: LOCATION_ROUTE_PAIR_HARD_DELETE_GRACE_PERIOD_NOT_REACHED."""
    return ProblemDetailError(
        409, "LOCATION_ROUTE_PAIR_HARD_DELETE_GRACE_PERIOD_NOT_REACHED", "Conflict", "Grace period not reached."
    )


def route_pair_usage_exists() -> ProblemDetailError:
    """Section 7.17: LOCATION_ROUTE_PAIR_USAGE_EXISTS."""
    return ProblemDetailError(409, "LOCATION_ROUTE_PAIR_USAGE_EXISTS", "Conflict", "Usage references exist.")


# ---------------------------------------------------------------------------
# Route version / display errors (Sections 7.12, 7.30)
# ---------------------------------------------------------------------------


def route_version_not_found() -> ProblemDetailError:
    """Section 7.12: LOCATION_ROUTE_VERSION_NOT_FOUND."""
    return ProblemDetailError(404, "LOCATION_ROUTE_VERSION_NOT_FOUND", "Not found", "Route version not found.")


def route_not_found() -> ProblemDetailError:
    """Section 7.29: ROUTE_NOT_FOUND."""
    return ProblemDetailError(404, "ROUTE_NOT_FOUND", "Not found", "Route not found.")


def route_ambiguous() -> ProblemDetailError:
    """Section 7.29: ROUTE_AMBIGUOUS."""
    return ProblemDetailError(422, "ROUTE_AMBIGUOUS", "Ambiguous", "Multiple routes match the given names.")


def display_invalid_lang() -> ProblemDetailError:
    """Section 7.30: LOCATION_DISPLAY_INVALID_LANG."""
    return ProblemDetailError(422, "LOCATION_DISPLAY_INVALID_LANG", "Validation error", "Unsupported lang value.")


# ---------------------------------------------------------------------------
# Import/export errors (Sections 7.22–7.28)
# ---------------------------------------------------------------------------


def import_file_too_large() -> ProblemDetailError:
    """Section 7.22: LOCATION_IMPORT_FILE_TOO_LARGE."""
    return ProblemDetailError(413, "LOCATION_IMPORT_FILE_TOO_LARGE", "Payload too large", "File exceeds 20 MB limit.")


def import_unsupported_file_type() -> ProblemDetailError:
    """Section 7.22: LOCATION_IMPORT_UNSUPPORTED_FILE_TYPE."""
    return ProblemDetailError(415, "LOCATION_IMPORT_UNSUPPORTED_FILE_TYPE", "Unsupported", "Only .xlsx accepted.")


def import_file_not_found() -> ProblemDetailError:
    """Section 7.23: LOCATION_IMPORT_FILE_NOT_FOUND."""
    return ProblemDetailError(404, "LOCATION_IMPORT_FILE_NOT_FOUND", "Not found", "File not found in storage.")


def import_duplicate_job() -> ProblemDetailError:
    """Section 7.23: LOCATION_IMPORT_DUPLICATE_JOB."""
    return ProblemDetailError(
        409, "LOCATION_IMPORT_DUPLICATE_JOB", "Conflict", "Duplicate import (same checksum + mode)."
    )


def export_scope_not_supported() -> ProblemDetailError:
    """Section 7.26: LOCATION_EXPORT_SCOPE_NOT_SUPPORTED."""
    return ProblemDetailError(
        422, "LOCATION_EXPORT_SCOPE_NOT_SUPPORTED", "Not supported", "PENDING_DRAFT_ONLY scope not available in V1."
    )


def storage_unavailable() -> ProblemDetailError:
    """Section 7.22: LOCATION_STORAGE_UNAVAILABLE."""
    return ProblemDetailError(503, "LOCATION_STORAGE_UNAVAILABLE", "Service unavailable", "Storage unavailable.")


# ---------------------------------------------------------------------------
# Idempotency errors (Section 16)
# ---------------------------------------------------------------------------


def idempotency_replay_mismatch() -> ProblemDetailError:
    """Section 16: LOCATION_IDEMPOTENCY_REPLAY_MISMATCH."""
    return ProblemDetailError(
        409, "LOCATION_IDEMPOTENCY_REPLAY_MISMATCH", "Conflict", "Same idempotency key used with different request."
    )


# ---------------------------------------------------------------------------
# Internal errors
# ---------------------------------------------------------------------------


def internal_error(detail: str = "") -> ProblemDetailError:
    """Generic internal server error."""
    return ProblemDetailError(500, "LOCATION_INTERNAL_ERROR", "Internal error", detail or "Unexpected error.")
