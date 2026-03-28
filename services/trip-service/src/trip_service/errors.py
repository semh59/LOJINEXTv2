"""Shared error handling following the Problem Details contract."""

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ProblemDetailError(Exception):
    """Raise from any handler to return a structured problem+json error."""

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


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Convert FastAPI validation failures into the trip-service problem format."""
    errors = []
    for err in exc.errors():
        location = ".".join(str(part) for part in err.get("loc", []))
        errors.append({"field": location, "message": err.get("msg", "Invalid value.")})
    problem = trip_validation_error("Request validation failed.", errors=errors)
    return await problem_detail_handler(request, problem)


def trip_not_found(trip_id: str) -> ProblemDetailError:
    return ProblemDetailError(404, "TRIP_NOT_FOUND", "Trip not found", f"Trip {trip_id} does not exist.")


def trip_auth_required() -> ProblemDetailError:
    return ProblemDetailError(401, "TRIP_AUTH_REQUIRED", "Authentication required", "Bearer token is required.")


def trip_auth_invalid(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(
        401,
        "TRIP_AUTH_INVALID",
        "Authentication failed",
        detail or "Bearer token is invalid or expired.",
    )


def trip_forbidden(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(
        403,
        "TRIP_FORBIDDEN",
        "Forbidden",
        detail or "You are not allowed to perform this action.",
    )


def trip_validation_error(detail: str, errors: list[dict[str, Any]] | None = None) -> ProblemDetailError:
    return ProblemDetailError(422, "TRIP_VALIDATION_ERROR", "Validation error", detail, errors=errors)


def trip_version_mismatch() -> ProblemDetailError:
    return ProblemDetailError(
        412,
        "TRIP_VERSION_MISMATCH",
        "Precondition failed",
        "If-Match header does not match current trip version.",
    )


def trip_if_match_required() -> ProblemDetailError:
    return ProblemDetailError(
        428,
        "TRIP_IF_MATCH_REQUIRED",
        "Precondition required",
        "If-Match header is required for this operation.",
    )


def trip_no_conflict(trip_no: str) -> ProblemDetailError:
    return ProblemDetailError(409, "TRIP_TRIP_NO_CONFLICT", "Conflict", f"Trip number {trip_no} already exists.")


def trip_source_reference_conflict(source_reference_key: str) -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "TRIP_SOURCE_REFERENCE_CONFLICT",
        "Conflict",
        f"Source reference {source_reference_key} already exists.",
    )


def trip_source_locked_field(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "TRIP_SOURCE_LOCKED_FIELD",
        "Field is locked by source contract",
        detail or "This field cannot be changed for the current trip source.",
    )


def trip_change_reason_required(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(
        422,
        "TRIP_CHANGE_REASON_REQUIRED",
        "Change reason required",
        detail or "A non-empty change_reason is required for this action.",
    )


def idempotency_payload_mismatch() -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "TRIP_IDEMPOTENCY_PAYLOAD_MISMATCH",
        "Idempotency conflict",
        "Same idempotency key was used with a different request payload.",
    )


def idempotency_in_flight() -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "TRIP_IDEMPOTENCY_IN_FLIGHT",
        "Idempotency in progress",
        "A request with this idempotency key is still being processed. Retry the request.",
    )


def invalid_status_transition(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(
        409, "TRIP_INVALID_STATUS_TRANSITION", "Invalid status transition", detail or "This transition is not allowed."
    )


def route_required_for_completion() -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "TRIP_ROUTE_REQUIRED_FOR_COMPLETION",
        "Route required",
        "Route must be READY before trip can be approved.",
    )


def trip_completion_requirements_missing(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "TRIP_COMPLETION_REQUIREMENTS_MISSING",
        "Trip not ready for completion",
        detail or "Trip is missing required route, duration, or payload fields needed for completion.",
    )


def trip_invalid_route_pair(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(
        422,
        "TRIP_INVALID_ROUTE_PAIR",
        "Invalid route pair",
        detail or "The provided route pair is missing, inactive, or incomplete.",
    )


def trip_invalid_date_window(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(
        422,
        "TRIP_INVALID_DATE_WINDOW",
        "Invalid date window",
        detail or "The requested date or time is outside the allowed window for this action.",
    )


def empty_return_already_exists() -> ProblemDetailError:
    return ProblemDetailError(
        409, "TRIP_EMPTY_RETURN_ALREADY_EXISTS", "Conflict", "An empty-return trip already exists for this base trip."
    )


def source_slip_conflict(source_slip_no: str) -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "TRIP_SOURCE_SLIP_CONFLICT",
        "Conflict",
        f"Slip {source_slip_no} already exists for TELEGRAM_TRIP_SLIP.",
    )


def invalid_base_for_empty_return(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "TRIP_INVALID_BASE_FOR_EMPTY_RETURN",
        "Invalid base trip",
        detail or "Base trip is not valid for empty-return creation.",
    )


def has_empty_return_child() -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "TRIP_HAS_EMPTY_RETURN_CHILD",
        "Cannot delete",
        "Trip has empty-return child trips. Delete child trips first.",
    )


def hard_delete_requires_soft_deleted() -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "TRIP_HARD_DELETE_REQUIRES_SOFT_DELETED",
        "Cannot hard delete",
        "Trip must be soft-deleted before it can be hard-deleted.",
    )


def trip_date_range_too_large(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(
        422,
        "TRIP_DATE_RANGE_TOO_LARGE",
        "Date range too large",
        detail or "The requested date range exceeds the allowed maximum.",
    )


def invalid_filter_combination(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(
        422, "TRIP_INVALID_FILTER_COMBINATION", "Invalid filter", detail or "Filter combination is not valid."
    )


def enrichment_already_running() -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "TRIP_ENRICHMENT_ALREADY_RUNNING",
        "Enrichment in progress",
        "Enrichment is currently running. Cannot retry.",
    )


def enrichment_retry_not_allowed() -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "TRIP_ENRICHMENT_RETRY_NOT_ALLOWED",
        "Retry not allowed",
        "Enrichment can only be retried while pending or failed.",
    )


def enrichment_terminal_state() -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "TRIP_ENRICHMENT_TERMINAL_STATE",
        "Retry not allowed",
        "READY or SKIPPED enrichment rows cannot be retried.",
    )


def endpoint_removed() -> ProblemDetailError:
    return ProblemDetailError(
        404,
        "TRIP_ENDPOINT_REMOVED",
        "Not found",
        "This endpoint is no longer served by trip-service.",
    )


def trip_dependency_unavailable(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(
        503,
        "TRIP_DEPENDENCY_UNAVAILABLE",
        "Dependency unavailable",
        detail or "A required downstream dependency is unavailable.",
    )


def trip_driver_overlap(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "TRIP_DRIVER_OVERLAP",
        "Trip overlap",
        detail or "Driver is already assigned to another overlapping trip.",
    )


def trip_vehicle_overlap(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "TRIP_VEHICLE_OVERLAP",
        "Trip overlap",
        detail or "Vehicle is already assigned to another overlapping trip.",
    )


def trip_trailer_overlap(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "TRIP_TRAILER_OVERLAP",
        "Trip overlap",
        detail or "Trailer is already assigned to another overlapping trip.",
    )


def internal_error(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(500, "TRIP_INTERNAL_ERROR", "Internal error", detail or "An unexpected error occurred.")
