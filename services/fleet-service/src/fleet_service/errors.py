"""Error model for Fleet Service (spec Section 14).

All non-2xx responses use application/problem+json format.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

logger = logging.getLogger("fleet_service.errors")


class ProblemDetailError(Exception):
    """Base exception that maps to an application/problem+json response."""

    def __init__(
        self,
        status: int,
        code: str,
        title: str,
        detail: str | None = None,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.errors = errors or []
        super().__init__(f"{code}: {title}")


# --- 400 ---
class IdempotencyKeyRequiredError(ProblemDetailError):
    """Idempotency-Key header is missing on create request."""

    def __init__(self) -> None:
        super().__init__(400, "IDEMPOTENCY_KEY_REQUIRED", "Idempotency-Key header is required for create endpoints")


class EtagRequiredError(ProblemDetailError):
    """If-Match header is missing (400, not 412 — missing != wrong value)."""

    def __init__(self, etag_type: str = "master") -> None:
        super().__init__(400, "ETAG_MISMATCH", f"If-Match header is required for {etag_type} mutations")


# --- 403 ---
class InsufficientRoleError(ProblemDetailError):
    """Caller has wrong role for the operation."""

    def __init__(self, required_role: str = "SUPER_ADMIN") -> None:
        super().__init__(403, "INSUFFICIENT_ROLE", f"This operation requires {required_role} role")


class UnauthorizedInternalCallError(ProblemDetailError):
    """SERVICE calling public or non-SERVICE calling internal."""

    def __init__(self) -> None:
        super().__init__(403, "UNAUTHORIZED_INTERNAL_CALL", "Endpoint type mismatch for caller role")


# --- 404 ---
class VehicleNotFoundError(ProblemDetailError):
    """Vehicle with given ID does not exist."""

    def __init__(self, vehicle_id: str = "") -> None:
        super().__init__(404, "VEHICLE_NOT_FOUND", "Vehicle not found", detail=f"vehicle_id={vehicle_id}")


class TrailerNotFoundError(ProblemDetailError):
    """Trailer with given ID does not exist."""

    def __init__(self, trailer_id: str = "") -> None:
        super().__init__(404, "TRAILER_NOT_FOUND", "Trailer not found", detail=f"trailer_id={trailer_id}")


class SpecNotInitializedError(ProblemDetailError):
    """Asset has no spec version created yet."""

    def __init__(self, asset_type: str = "VEHICLE") -> None:
        super().__init__(404, "SPEC_NOT_INITIALIZED", f"{asset_type} has no technical specification initialized")


class SpecNotFoundForInstantError(ProblemDetailError):
    """No spec window covers the requested timestamp."""

    def __init__(self, at: str = "") -> None:
        super().__init__(404, "SPEC_NOT_FOUND_FOR_INSTANT", f"No spec window covers timestamp {at}")


# --- 409 ---
class VehiclePlateAlreadyExistsError(ProblemDetailError):
    """Normalized plate already in use by another active vehicle."""

    def __init__(self) -> None:
        super().__init__(
            409,
            "VEHICLE_PLATE_ALREADY_EXISTS",
            "Normalized plate already in use by another active vehicle",
        )


class TrailerPlateAlreadyExistsError(ProblemDetailError):
    """Normalized plate already in use by another active trailer."""

    def __init__(self) -> None:
        super().__init__(
            409,
            "TRAILER_PLATE_ALREADY_EXISTS",
            "Normalized plate already in use by another active trailer",
        )


class VehicleAssetCodeAlreadyExistsError(ProblemDetailError):
    """Asset code already in use by another vehicle."""

    def __init__(self) -> None:
        super().__init__(
            409,
            "VEHICLE_ASSET_CODE_ALREADY_EXISTS",
            "Asset code already in use by another vehicle",
        )


class TrailerAssetCodeAlreadyExistsError(ProblemDetailError):
    """Asset code already in use by another trailer."""

    def __init__(self) -> None:
        super().__init__(
            409,
            "TRAILER_ASSET_CODE_ALREADY_EXISTS",
            "Asset code already in use by another trailer",
        )


class AssetReferencedHardDeleteForbiddenError(ProblemDetailError):
    """Asset is still referenced by trips — cannot hard-delete."""

    def __init__(self) -> None:
        super().__init__(
            409,
            "ASSET_REFERENCED_HARD_DELETE_FORBIDDEN",
            "Asset is referenced by trips and cannot be hard-deleted",
        )


class IdempotencyHashMismatchError(ProblemDetailError):
    """Idempotency key reused with different request body."""

    def __init__(self) -> None:
        super().__init__(
            409,
            "IDEMPOTENCY_HASH_MISMATCH",
            "Idempotency key reused with different request body",
        )


# --- 412 ---
class EtagMismatchError(ProblemDetailError):
    """Master If-Match header does not match current row_version."""

    def __init__(self) -> None:
        super().__init__(
            412,
            "ETAG_MISMATCH",
            "Master If-Match header does not match current row_version",
        )


class SpecEtagMismatchError(ProblemDetailError):
    """Spec If-Match header does not match current spec_stream_version."""

    def __init__(self) -> None:
        super().__init__(
            412,
            "SPEC_ETAG_MISMATCH",
            "Spec If-Match header does not match current spec_stream_version",
        )


# --- 422 ---
class VehicleInactiveError(ProblemDetailError):
    """Vehicle is inactive."""

    def __init__(self) -> None:
        super().__init__(
            422,
            "VEHICLE_INACTIVE",
            "Vehicle is inactive and cannot be used for new operations",
        )


class TrailerInactiveError(ProblemDetailError):
    """Trailer is inactive."""

    def __init__(self) -> None:
        super().__init__(
            422,
            "TRAILER_INACTIVE",
            "Trailer is inactive and cannot be used for new operations",
        )


class VehicleSoftDeletedError(ProblemDetailError):
    """Vehicle is soft-deleted."""

    def __init__(self) -> None:
        super().__init__(422, "VEHICLE_SOFT_DELETED", "Vehicle is soft-deleted")


class TrailerSoftDeletedError(ProblemDetailError):
    """Trailer is soft-deleted."""

    def __init__(self) -> None:
        super().__init__(422, "TRAILER_SOFT_DELETED", "Trailer is soft-deleted")


class AssetAlreadyInTargetStateError(ProblemDetailError):
    """Asset is already in the requested target state."""

    def __init__(self, current_state: str = "") -> None:
        super().__init__(
            422,
            "ASSET_ALREADY_IN_TARGET_STATE",
            f"Asset is already in the target state: {current_state}",
        )


class InvalidStatusTransitionError(ProblemDetailError):
    """Lifecycle transition is not permitted."""

    def __init__(self, detail: str = "") -> None:
        super().__init__(
            422,
            "INVALID_STATUS_TRANSITION",
            "Lifecycle transition not permitted",
            detail=detail,
        )


class AssetInactiveOrDeletedError(ProblemDetailError):
    """Cannot create spec version for inactive or soft-deleted asset."""

    def __init__(self) -> None:
        super().__init__(
            422,
            "ASSET_INACTIVE_OR_DELETED",
            "Cannot create spec version for inactive or soft-deleted asset",
        )


class InvalidSpecWindowError(ProblemDetailError):
    """Spec window is invalid (effective_to <= effective_from)."""

    def __init__(self) -> None:
        super().__init__(
            422,
            "INVALID_SPEC_WINDOW",
            "effective_to_utc must be after effective_from_utc",
        )


class SpecVersionOverlapError(ProblemDetailError):
    """New spec window overlaps an existing version window."""

    def __init__(self) -> None:
        super().__init__(
            422,
            "SPEC_VERSION_OVERLAP",
            "New spec window overlaps an existing version window",
        )


class InputValidationError(ProblemDetailError):
    """Generic input validation failure."""

    def __init__(self, errors: list[dict[str, Any]] | None = None) -> None:
        super().__init__(422, "VALIDATION_ERROR", "Input validation failed", errors=errors)


# --- 503 ---
class DependencyUnavailableError(ProblemDetailError):
    """Required upstream service is unavailable."""

    def __init__(self, target: str = "") -> None:
        super().__init__(
            503,
            "DEPENDENCY_UNAVAILABLE",
            f"Required upstream service unavailable: {target}",
        )


# --- Exception handlers ---


async def problem_detail_handler(request: Request, exc: ProblemDetailError) -> JSONResponse:
    """Convert ProblemDetailError to application/problem+json response."""
    request_id = getattr(request.state, "request_id", None)
    body: dict[str, Any] = {
        "type": f"https://fleet-service/errors/{exc.code}",
        "title": exc.title,
        "status": exc.status,
        "code": exc.code,
        "request_id": request_id,
    }
    if exc.detail:
        body["detail"] = exc.detail
    if exc.errors:
        body["errors"] = exc.errors

    return JSONResponse(
        status_code=exc.status,
        content=body,
        media_type="application/problem+json",
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Convert FastAPI/Pydantic validation errors to application/problem+json format."""
    request_id = getattr(request.state, "request_id", None)
    errors = []
    for err in exc.errors():
        field = ".".join(str(loc) for loc in err["loc"] if loc != "body")
        errors.append({"field": field, "code": err["type"], "message": err["msg"]})

    return JSONResponse(
        status_code=422,
        content={
            "type": "https://fleet-service/errors/VALIDATION_ERROR",
            "title": "Input validation failed",
            "status": 422,
            "code": "VALIDATION_ERROR",
            "request_id": request_id,
            "errors": errors,
        },
        media_type="application/problem+json",
    )
