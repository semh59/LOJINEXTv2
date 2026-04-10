"""Shared error handling following the Location Service problem-details contract.

All non-2xx responses use application/problem+json with stable extension fields.
"""

import logging
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("location_service.errors")


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
        "type": f"https://errors.lojinext.com/{exc.code}",
        "title": exc.title,
        "status": exc.status,
        "detail": exc.detail,
        "instance": exc.instance or str(request.url.path),
        "code": exc.code,
        "request_id": request_id,
        "errors": exc.errors,
    }
    return JSONResponse(status_code=exc.status, content=body, media_type="application/problem+json")


async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Convert unhandled exceptions into a stable problem+json response."""
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception("Unhandled Location Service exception", extra={"request_id": request_id})
    return await problem_detail_handler(request, internal_error())


def request_validation_error(errors: list[dict[str, Any]]) -> ProblemDetailError:
    """Return the stable generic request validation error."""
    return ProblemDetailError(
        422,
        "LOCATION_REQUEST_VALIDATION_ERROR",
        "Validation error",
        "Request validation failed.",
        errors=errors,
    )


def _normalize_validation_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Normalize FastAPI/Pydantic validation errors into a stable payload shape."""
    normalized: list[dict[str, Any]] = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err.get("loc", ()))
        normalized.append(
            {
                "field": loc,
                "code": err.get("type", "validation_error"),
                "message": err.get("msg", "Validation error."),
            }
        )
    return normalized


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return problem+json for request validation failures."""
    errors = _normalize_validation_errors(exc)
    immutable_fields = {"body.code", "body.latitude_6dp", "body.longitude_6dp"}
    if request.url.path.startswith("/v1/points/") and any(err["field"] in immutable_fields for err in errors):
        problem = point_immutable_field_modification()
        problem.errors = errors
        return await problem_detail_handler(request, problem)

    return await problem_detail_handler(request, request_validation_error(errors))


# ---------------------------------------------------------------------------
# Point errors
# ---------------------------------------------------------------------------


def point_not_found(location_id: str) -> ProblemDetailError:
    return ProblemDetailError(404, "LOCATION_POINT_NOT_FOUND", "Point not found", f"Point {location_id} not found.")


def point_code_conflict(code: str) -> ProblemDetailError:
    return ProblemDetailError(409, "LOCATION_POINT_CODE_CONFLICT", "Conflict", f"Point code '{code}' already exists.")


def point_name_conflict(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "LOCATION_POINT_NAME_CONFLICT",
        "Conflict",
        detail or "Normalized name conflicts with existing point.",
    )


def point_coordinate_conflict() -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "LOCATION_POINT_COORDINATE_CONFLICT",
        "Conflict",
        "Coordinates conflict with existing point.",
    )


def point_invalid_coordinates(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(
        422,
        "LOCATION_POINT_INVALID_COORDINATES",
        "Invalid coordinates",
        detail or "Coordinates out of range or null island.",
    )


def point_name_blank() -> ProblemDetailError:
    return ProblemDetailError(422, "LOCATION_POINT_NAME_BLANK", "Validation error", "Point name must not be blank.")


def point_immutable_field_modification() -> ProblemDetailError:
    return ProblemDetailError(
        422,
        "LOCATION_POINT_IMMUTABLE_FIELD_MODIFICATION",
        "Immutable field",
        "Cannot modify immutable fields: location_id, code, latitude, longitude, normalized_name_*.",
    )


def point_in_use_by_active_pair() -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "LOCATION_POINT_IN_USE_BY_ACTIVE_PAIR",
        "Conflict",
        "Point is referenced by an ACTIVE or DRAFT pair; cannot deactivate.",
    )


def point_version_mismatch() -> ProblemDetailError:
    return ProblemDetailError(412, "LOCATION_POINT_VERSION_MISMATCH", "Precondition failed", "ETag does not match.")


def if_match_required() -> ProblemDetailError:
    return ProblemDetailError(428, "LOCATION_IF_MATCH_REQUIRED", "Precondition required", "If-Match header required.")


def location_auth_required() -> ProblemDetailError:
    return ProblemDetailError(401, "LOCATION_AUTH_REQUIRED", "Authentication required", "Bearer token is required.")


def location_auth_invalid(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(
        401,
        "LOCATION_AUTH_INVALID",
        "Authentication failed",
        detail or "Bearer token is invalid or expired.",
    )


def location_forbidden(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(
        403,
        "LOCATION_FORBIDDEN",
        "Forbidden",
        detail or "You are not allowed to perform this action.",
    )


def endpoint_removed() -> ProblemDetailError:
    return ProblemDetailError(
        404,
        "LOCATION_ENDPOINT_REMOVED",
        "Not found",
        "This endpoint is no longer served by location-service.",
    )


# ---------------------------------------------------------------------------
# Route pair errors
# ---------------------------------------------------------------------------


def route_pair_not_found(pair_id: str = "") -> ProblemDetailError:
    return ProblemDetailError(
        404,
        "LOCATION_ROUTE_PAIR_NOT_FOUND",
        "Not found",
        f"Route pair {pair_id} not found." if pair_id else "Route pair not found.",
    )


def route_pair_already_exists_active() -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "LOCATION_ROUTE_PAIR_ALREADY_EXISTS_ACTIVE",
        "Conflict",
        "A route pair already exists for this origin/destination/profile (ACTIVE or DRAFT).",
    )


def route_pair_already_exists_deleted() -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "LOCATION_ROUTE_PAIR_ALREADY_EXISTS_DELETED",
        "Conflict",
        "A soft-deleted pair exists for this origin/destination/profile. Restore is not available in V1.",
    )


def route_origin_equals_destination() -> ProblemDetailError:
    return ProblemDetailError(
        422,
        "LOCATION_ROUTE_ORIGIN_EQUALS_DESTINATION",
        "Validation error",
        "Origin and destination must be different points.",
    )


def point_inactive_for_new_pair() -> ProblemDetailError:
    return ProblemDetailError(
        409, "LOCATION_POINT_INACTIVE_FOR_NEW_PAIR", "Conflict", "Cannot create pair with inactive point."
    )


def route_pair_version_mismatch() -> ProblemDetailError:
    return ProblemDetailError(412, "LOCATION_ROUTE_PAIR_VERSION_MISMATCH", "Precondition failed", "ETag mismatch.")


def invalid_filter_combination(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(
        422,
        "LOCATION_INVALID_FILTER_COMBINATION",
        "Validation error",
        detail or "The provided filters cannot be combined.",
    )


# ---------------------------------------------------------------------------
# Processing errors
# ---------------------------------------------------------------------------


def route_pair_already_running() -> ProblemDetailError:
    return ProblemDetailError(409, "LOCATION_ROUTE_PAIR_ALREADY_RUNNING", "Conflict", "A run is already active.")


def route_pair_pending_draft_exists() -> ProblemDetailError:
    return ProblemDetailError(409, "LOCATION_ROUTE_PAIR_PENDING_DRAFT_EXISTS", "Conflict", "Pending draft exists.")


def route_pair_soft_deleted() -> ProblemDetailError:
    return ProblemDetailError(409, "LOCATION_ROUTE_PAIR_SOFT_DELETED", "Conflict", "Pair is soft-deleted.")


def route_pair_already_active_use_refresh() -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "LOCATION_ROUTE_PAIR_ALREADY_ACTIVE_USE_REFRESH",
        "Conflict",
        "Already active - use refresh instead.",
    )


def route_pair_not_active_use_calculate() -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "LOCATION_ROUTE_PAIR_NOT_ACTIVE_USE_CALCULATE",
        "Conflict",
        "Not yet active - use calculate instead.",
    )


def processing_run_not_found(run_id: str = "") -> ProblemDetailError:
    return ProblemDetailError(404, "LOCATION_PROCESSING_RUN_NOT_FOUND", "Not found", "Processing run not found.")


def run_not_stuck() -> ProblemDetailError:
    return ProblemDetailError(409, "LOCATION_RUN_NOT_STUCK", "Conflict", "Run is not stuck (SLA not reached).")


# ---------------------------------------------------------------------------
# Approval / draft errors
# ---------------------------------------------------------------------------


def route_pair_pending_draft_not_found() -> ProblemDetailError:
    return ProblemDetailError(404, "LOCATION_ROUTE_PAIR_PENDING_DRAFT_NOT_FOUND", "Not found", "No pending draft.")


def route_pair_draft_run_mismatch() -> ProblemDetailError:
    return ProblemDetailError(409, "LOCATION_ROUTE_PAIR_DRAFT_RUN_MISMATCH", "Conflict", "Run ID does not match.")


def route_pair_not_ready_for_approval() -> ProblemDetailError:
    return ProblemDetailError(409, "LOCATION_ROUTE_PAIR_NOT_READY_FOR_APPROVAL", "Conflict", "No pending draft.")


def route_pair_version_conflict() -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "LOCATION_ROUTE_PAIR_VERSION_CONFLICT",
        "Conflict",
        "Version numbers do not match pending draft.",
    )


def version_segment_count_mismatch() -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "LOCATION_VERSION_SEGMENT_COUNT_MISMATCH",
        "Conflict",
        "Segment count in DB does not match version row.",
    )


def route_pair_approve_run_mismatch() -> ProblemDetailError:
    return ProblemDetailError(422, "LOCATION_ROUTE_PAIR_APPROVE_RUN_MISMATCH", "Validation error", "Run mismatch.")


def route_pair_draft_hash_mismatch() -> ProblemDetailError:
    return ProblemDetailError(422, "LOCATION_ROUTE_PAIR_DRAFT_HASH_MISMATCH", "Validation error", "Hash mismatch.")


def route_pair_no_pending_draft() -> ProblemDetailError:
    return ProblemDetailError(409, "LOCATION_ROUTE_PAIR_NO_PENDING_DRAFT", "Conflict", "No pending draft to discard.")


def route_pair_run_in_progress() -> ProblemDetailError:
    return ProblemDetailError(409, "LOCATION_ROUTE_PAIR_RUN_IN_PROGRESS", "Conflict", "Run is still in progress.")


def route_pair_discard_run_mismatch() -> ProblemDetailError:
    return ProblemDetailError(422, "LOCATION_ROUTE_PAIR_DISCARD_RUN_MISMATCH", "Validation error", "Run mismatch.")


# ---------------------------------------------------------------------------
# Delete errors
# ---------------------------------------------------------------------------


def route_pair_already_soft_deleted() -> ProblemDetailError:
    return ProblemDetailError(409, "LOCATION_ROUTE_PAIR_ALREADY_SOFT_DELETED", "Conflict", "Already soft-deleted.")


def route_pair_not_soft_deleted() -> ProblemDetailError:
    return ProblemDetailError(409, "LOCATION_ROUTE_PAIR_NOT_SOFT_DELETED", "Conflict", "Pair is not soft-deleted.")


def route_pair_hard_delete_blocked_was_active() -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "LOCATION_ROUTE_PAIR_HARD_DELETE_BLOCKED_WAS_ACTIVE",
        "Conflict",
        "Pair has activation history; hard delete blocked.",
    )


def route_pair_hard_delete_grace_period_not_reached() -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "LOCATION_ROUTE_PAIR_HARD_DELETE_GRACE_PERIOD_NOT_REACHED",
        "Conflict",
        "Grace period not reached.",
    )


def route_pair_usage_exists() -> ProblemDetailError:
    return ProblemDetailError(409, "LOCATION_ROUTE_PAIR_USAGE_EXISTS", "Conflict", "Usage references exist.")


# ---------------------------------------------------------------------------
# Route version / display errors
# ---------------------------------------------------------------------------


def route_version_not_found() -> ProblemDetailError:
    return ProblemDetailError(404, "LOCATION_ROUTE_VERSION_NOT_FOUND", "Not found", "Route version not found.")


def route_not_found() -> ProblemDetailError:
    return ProblemDetailError(404, "ROUTE_NOT_FOUND", "Not found", "Route not found.")


def route_resolution_not_found() -> ProblemDetailError:
    return ProblemDetailError(
        404,
        "LOCATION_ROUTE_RESOLUTION_NOT_FOUND",
        "Not found",
        "No active route matches the provided origin/destination/profile.",
    )


def route_ambiguous() -> ProblemDetailError:
    return ProblemDetailError(422, "ROUTE_AMBIGUOUS", "Ambiguous", "Multiple routes match the given names.")


def display_invalid_lang() -> ProblemDetailError:
    return ProblemDetailError(422, "LOCATION_DISPLAY_INVALID_LANG", "Validation error", "Unsupported lang value.")


# ---------------------------------------------------------------------------
# Idempotency / internal errors
# ---------------------------------------------------------------------------


def idempotency_replay_mismatch() -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "LOCATION_IDEMPOTENCY_REPLAY_MISMATCH",
        "Conflict",
        "Same idempotency key used with different request.",
    )


def internal_error(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(500, "LOCATION_INTERNAL_ERROR", "Internal error", detail or "Unexpected error.")
