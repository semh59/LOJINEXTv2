"""Shared error handling following the Problem Details contract (spec Section 3)."""

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
        "type": f"https://driver-service/errors/{exc.code}",
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
    """Convert FastAPI validation failures into the driver-service problem format."""
    errors = []
    for err in exc.errors():
        location = ".".join(str(part) for part in err.get("loc", []))
        errors.append({"field": location, "message": err.get("msg", "Invalid value.")})
    problem = driver_validation_error("Request validation failed.", errors=errors)
    return await problem_detail_handler(request, problem)


# ---- Auth errors ----


def driver_auth_required() -> ProblemDetailError:
    return ProblemDetailError(401, "DRIVER_AUTH_REQUIRED", "Authentication required", "Bearer token is required.")


def driver_auth_invalid(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(
        401, "DRIVER_AUTH_INVALID", "Authentication failed", detail or "Bearer token is invalid or expired."
    )


def driver_forbidden(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(
        403, "DRIVER_FORBIDDEN", "Forbidden", detail or "You are not allowed to perform this action."
    )


def driver_internal_auth_required() -> ProblemDetailError:
    return ProblemDetailError(
        401, "DRIVER_INTERNAL_AUTH_REQUIRED", "Authentication required", "Service bearer token is required."
    )


def driver_internal_forbidden(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(403, "DRIVER_INTERNAL_FORBIDDEN", "Forbidden", detail or "Service token not authorized.")


# ---- Validation errors ----


def driver_validation_error(detail: str, errors: list[dict[str, Any]] | None = None) -> ProblemDetailError:
    return ProblemDetailError(422, "DRIVER_VALIDATION_ERROR", "Validation error", detail, errors=errors)


def driver_invalid_pagination(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(
        422, "DRIVER_INVALID_PAGINATION", "Invalid pagination", detail or "Pagination parameters are invalid."
    )


def driver_inactive_reason_required() -> ProblemDetailError:
    return ProblemDetailError(
        422,
        "DRIVER_INACTIVE_REASON_REQUIRED",
        "Validation error",
        "inactive_reason is required for manual inactivation.",
    )


def driver_soft_delete_reason_required() -> ProblemDetailError:
    return ProblemDetailError(
        422, "DRIVER_SOFT_DELETE_REASON_REQUIRED", "Validation error", "reason is required for soft delete."
    )


def driver_lookup_mode_invalid() -> ProblemDetailError:
    return ProblemDetailError(
        422, "DRIVER_LOOKUP_MODE_INVALID", "Validation error", "Exactly one lookup key must be provided."
    )


def driver_bulk_limit_exceeded(limit: int) -> ProblemDetailError:
    return ProblemDetailError(
        422, "DRIVER_BULK_LIMIT_EXCEEDED", "Validation error", f"Maximum {limit} driver IDs allowed per request."
    )


def driver_import_validation_error(detail: str, errors: list[dict[str, Any]] | None = None) -> ProblemDetailError:
    return ProblemDetailError(422, "DRIVER_IMPORT_VALIDATION_ERROR", "Import validation error", detail, errors=errors)


def driver_import_batch_too_large(limit: int) -> ProblemDetailError:
    return ProblemDetailError(
        422, "DRIVER_IMPORT_BATCH_TOO_LARGE", "Batch too large", f"Import batch exceeds maximum of {limit} rows."
    )


def driver_merge_source_equals_target() -> ProblemDetailError:
    return ProblemDetailError(
        422, "DRIVER_MERGE_SOURCE_EQUALS_TARGET", "Validation error", "Source and target driver IDs must be different."
    )


def driver_merge_invalid(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(
        422, "DRIVER_MERGE_INVALID", "Merge validation error", detail or "Merge request is invalid."
    )


# ---- Not found ----


def driver_not_found(driver_id: str = "") -> ProblemDetailError:
    detail = f"Driver {driver_id} does not exist." if driver_id else "Driver not found."
    return ProblemDetailError(404, "DRIVER_NOT_FOUND", "Driver not found", detail)


# ---- Conflict errors ----


def driver_phone_already_exists() -> ProblemDetailError:
    return ProblemDetailError(
        409, "DRIVER_PHONE_ALREADY_EXISTS", "Conflict", "A live driver with this phone number already exists."
    )


def driver_telegram_already_exists() -> ProblemDetailError:
    return ProblemDetailError(
        409, "DRIVER_TELEGRAM_ALREADY_EXISTS", "Conflict", "A live driver with this Telegram user ID already exists."
    )


def driver_company_code_already_exists() -> ProblemDetailError:
    return ProblemDetailError(
        409,
        "DRIVER_COMPANY_CODE_ALREADY_EXISTS",
        "Conflict",
        "A live driver with this company driver code already exists.",
    )


def driver_already_soft_deleted() -> ProblemDetailError:
    return ProblemDetailError(409, "DRIVER_ALREADY_SOFT_DELETED", "Conflict", "Driver is already soft-deleted.")


def driver_lookup_ambiguous() -> ProblemDetailError:
    return ProblemDetailError(409, "DRIVER_LOOKUP_AMBIGUOUS", "Conflict", "Multiple drivers match the lookup criteria.")


def driver_import_conflict(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(
        409, "DRIVER_IMPORT_CONFLICT", "Import conflict", detail or "Import encountered a conflict."
    )


def driver_merge_source_has_active_trips() -> ProblemDetailError:
    return ProblemDetailError(
        409, "DRIVER_MERGE_SOURCE_HAS_ACTIVE_TRIPS", "Conflict", "Source driver has active trips and cannot be merged."
    )


def driver_merge_blocked(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(409, "DRIVER_MERGE_BLOCKED", "Merge blocked", detail or "Merge is blocked.")


def driver_hard_delete_blocked_by_history() -> ProblemDetailError:
    return ProblemDetailError(
        409, "DRIVER_HARD_DELETE_BLOCKED_BY_HISTORY", "Conflict", "Driver has active or historical trip references."
    )


# ---- Precondition errors ----


def driver_version_mismatch() -> ProblemDetailError:
    return ProblemDetailError(
        412, "DRIVER_VERSION_MISMATCH", "Precondition failed", "If-Match header does not match current driver version."
    )


def driver_if_match_required() -> ProblemDetailError:
    return ProblemDetailError(
        428, "DRIVER_IF_MATCH_REQUIRED", "Precondition required", "If-Match header is required for this operation."
    )


# ---- Internal / Dependency errors ----


def driver_internal_error(detail: str = "") -> ProblemDetailError:
    return ProblemDetailError(500, "DRIVER_INTERNAL_ERROR", "Internal error", detail or "An unexpected error occurred.")


def driver_trip_check_unavailable() -> ProblemDetailError:
    return ProblemDetailError(
        503,
        "DRIVER_TRIP_CHECK_UNAVAILABLE",
        "Dependency unavailable",
        "Trip Service is unavailable for reference check.",
    )
