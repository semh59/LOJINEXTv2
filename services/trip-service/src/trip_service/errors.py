"""Shared error handling following V8 Section 8.7 — Problem Details Contract.

All non-2xx responses use application/problem+json with stable extension fields.
"""

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class ProblemDetailError(Exception):
    """Raise from any handler to return a structured problem+json error.

    V8 Section 8.7: code, request_id, optional errors array.
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


async def problem_detail_handler(request: Request, exc: ProblemDetailError) -> JSONResponse:
    """Convert ProblemDetail exceptions into RFC 9457 problem+json responses."""
    request_id = getattr(request.state, "request_id", "unknown")
    body: dict[str, Any] = {
        "type": f"https://trip-service/errors/{exc.code}",
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


# --- Convenience error factories for all V8 Section 22 error codes ---


def trip_not_found(trip_id: str) -> ProblemDetailError:
    """V8: TRIP_NOT_FOUND."""
    return ProblemDetailError(404, "TRIP_NOT_FOUND", "Trip not found", f"Trip {trip_id} does not exist.")


def trip_validation_error(detail: str, errors: list[dict[str, Any]] | None = None) -> ProblemDetailError:
    """V8: TRIP_VALIDATION_ERROR."""
    return ProblemDetailError(422, "TRIP_VALIDATION_ERROR", "Validation error", detail, errors=errors)


def trip_version_mismatch() -> ProblemDetailError:
    """V8: TRIP_VERSION_MISMATCH."""
    return ProblemDetailError(
        412,
        "TRIP_VERSION_MISMATCH",
        "Precondition failed",
        "If-Match header does not match current trip version.",
    )


def trip_if_match_required() -> ProblemDetailError:
    """V8: TRIP_IF_MATCH_REQUIRED."""
    return ProblemDetailError(
        428,
        "TRIP_IF_MATCH_REQUIRED",
        "Precondition required",
        "If-Match header is required for this operation.",
    )


def trip_no_conflict(trip_no: str) -> ProblemDetailError:
    """V8: TRIP_TRIP_NO_CONFLICT."""
    return ProblemDetailError(409, "TRIP_TRIP_NO_CONFLICT", "Conflict", f"Trip number {trip_no} already exists.")


def idempotency_payload_mismatch() -> ProblemDetailError:
    """V8: TRIP_IDEMPOTENCY_PAYLOAD_MISMATCH."""
    return ProblemDetailError(
        409,
        "TRIP_IDEMPOTENCY_PAYLOAD_MISMATCH",
        "Idempotency conflict",
        "Same idempotency key was used with a different request payload.",
    )


def invalid_status_transition(detail: str = "") -> ProblemDetailError:
    """V8: TRIP_INVALID_STATUS_TRANSITION."""
    return ProblemDetailError(
        409, "TRIP_INVALID_STATUS_TRANSITION", "Invalid status transition", detail or "This transition is not allowed."
    )


def route_required_for_completion() -> ProblemDetailError:
    """V8: TRIP_ROUTE_REQUIRED_FOR_COMPLETION."""
    return ProblemDetailError(
        409,
        "TRIP_ROUTE_REQUIRED_FOR_COMPLETION",
        "Route required",
        "Route must be READY before trip can be approved.",
    )


def weather_required_for_completion() -> ProblemDetailError:
    """V8: TRIP_WEATHER_REQUIRED_FOR_COMPLETION."""
    return ProblemDetailError(
        409,
        "TRIP_WEATHER_REQUIRED_FOR_COMPLETION",
        "Weather required",
        "Weather must be READY before trip can be approved.",
    )


def empty_return_already_exists() -> ProblemDetailError:
    """V8: TRIP_EMPTY_RETURN_ALREADY_EXISTS."""
    return ProblemDetailError(
        409, "TRIP_EMPTY_RETURN_ALREADY_EXISTS", "Conflict", "An empty-return trip already exists for this base trip."
    )


def invalid_base_for_empty_return(detail: str = "") -> ProblemDetailError:
    """V8: TRIP_INVALID_BASE_FOR_EMPTY_RETURN."""
    return ProblemDetailError(
        409,
        "TRIP_INVALID_BASE_FOR_EMPTY_RETURN",
        "Invalid base trip",
        detail or "Base trip is not valid for empty-return creation.",
    )


def has_empty_return_child() -> ProblemDetailError:
    """V8: TRIP_HAS_EMPTY_RETURN_CHILD."""
    return ProblemDetailError(
        409,
        "TRIP_HAS_EMPTY_RETURN_CHILD",
        "Cannot delete",
        "Trip has empty-return child trips. Delete child trips first.",
    )


def invalid_filter_combination(detail: str = "") -> ProblemDetailError:
    """V8: TRIP_INVALID_FILTER_COMBINATION."""
    return ProblemDetailError(
        422, "TRIP_INVALID_FILTER_COMBINATION", "Invalid filter", detail or "Filter combination is not valid."
    )


def enrichment_already_running() -> ProblemDetailError:
    """V8: TRIP_ENRICHMENT_ALREADY_RUNNING."""
    return ProblemDetailError(
        409,
        "TRIP_ENRICHMENT_ALREADY_RUNNING",
        "Enrichment in progress",
        "Enrichment is currently running. Cannot retry.",
    )


def import_unsupported_file_type() -> ProblemDetailError:
    """V8: TRIP_IMPORT_UNSUPPORTED_FILE_TYPE."""
    return ProblemDetailError(
        415, "TRIP_IMPORT_UNSUPPORTED_FILE_TYPE", "Unsupported file type", "Only .xlsx files are accepted."
    )


def import_job_not_found(job_id: str) -> ProblemDetailError:
    """V8: TRIP_IMPORT_JOB_NOT_FOUND."""
    return ProblemDetailError(404, "TRIP_IMPORT_JOB_NOT_FOUND", "Not found", f"Import job {job_id} not found.")


def export_job_not_found(job_id: str) -> ProblemDetailError:
    """V8: TRIP_EXPORT_JOB_NOT_FOUND."""
    return ProblemDetailError(404, "TRIP_EXPORT_JOB_NOT_FOUND", "Not found", f"Export job {job_id} not found.")


def export_not_ready() -> ProblemDetailError:
    """V8: TRIP_EXPORT_NOT_READY."""
    return ProblemDetailError(409, "TRIP_EXPORT_NOT_READY", "Not ready", "Export job is not completed yet.")


def export_file_expired() -> ProblemDetailError:
    """V8: TRIP_EXPORT_FILE_EXPIRED."""
    return ProblemDetailError(410, "TRIP_EXPORT_FILE_EXPIRED", "Gone", "Export file has expired.")


def export_file_not_found() -> ProblemDetailError:
    """V8: TRIP_EXPORT_FILE_NOT_FOUND."""
    return ProblemDetailError(404, "TRIP_EXPORT_FILE_NOT_FOUND", "Not found", "Export file not found in storage.")


def storage_unavailable() -> ProblemDetailError:
    """V8: TRIP_STORAGE_UNAVAILABLE."""
    return ProblemDetailError(503, "TRIP_STORAGE_UNAVAILABLE", "Service unavailable", "Object storage is unavailable.")


def internal_error(detail: str = "") -> ProblemDetailError:
    """V8: TRIP_INTERNAL_ERROR."""
    return ProblemDetailError(500, "TRIP_INTERNAL_ERROR", "Internal error", detail or "An unexpected error occurred.")
