"""Shared error handling following the Problem Details contract (RFC 9457)."""

from __future__ import annotations

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


async def problem_detail_handler(
    request: Request, exc: ProblemDetailError
) -> JSONResponse:
    """Convert ProblemDetail exceptions into RFC 9457 problem+json responses."""
    request_id = getattr(request.state, "request_id", "unknown")
    body: dict[str, Any] = {
        "type": f"https://identity-service/errors/{exc.code}",
        "title": exc.title,
        "status": exc.status,
        "detail": exc.detail,
        "instance": exc.instance or str(request.url.path),
        "code": exc.code,
        "request_id": request_id,
    }
    if exc.errors:
        body["errors"] = exc.errors
    return JSONResponse(
        status_code=exc.status, content=body, media_type="application/problem+json"
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Convert FastAPI validation failures into the identity-service problem format."""
    errors = []
    for err in exc.errors():
        location = ".".join(str(part) for part in err.get("loc", []))
        errors.append({"field": location, "message": err.get("msg", "Invalid value.")})
    problem = identity_validation_error("Request validation failed.", errors=errors)
    return await problem_detail_handler(request, problem)


def identity_validation_error(
    detail: str, errors: list[dict[str, Any]] | None = None
) -> ProblemDetailError:
    return ProblemDetailError(
        422, "IDENTITY_VALIDATION_ERROR", "Validation error", detail, errors=errors
    )


def identity_not_found(detail: str) -> ProblemDetailError:
    return ProblemDetailError(404, "IDENTITY_NOT_FOUND", "Resource not found", detail)


def identity_unauthorized(
    detail: str = "Authentication required",
) -> ProblemDetailError:
    return ProblemDetailError(401, "IDENTITY_UNAUTHORIZED", "Unauthorized", detail)


def identity_forbidden(detail: str = "Access denied") -> ProblemDetailError:
    return ProblemDetailError(403, "IDENTITY_FORBIDDEN", "Forbidden", detail)


def identity_rate_limited(detail: str = "Too many requests") -> ProblemDetailError:
    return ProblemDetailError(429, "IDENTITY_RATE_LIMITED", "Rate limited", detail)


def identity_conflict(detail: str) -> ProblemDetailError:
    return ProblemDetailError(409, "IDENTITY_CONFLICT", "Conflict", detail)


def internal_error(detail: str = "An unexpected error occurred") -> ProblemDetailError:
    return ProblemDetailError(500, "IDENTITY_INTERNAL_ERROR", "Internal error", detail)
