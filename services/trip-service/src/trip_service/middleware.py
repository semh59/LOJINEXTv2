"""Shared middleware for Trip Service.

Implements V8 Sections 8.2 (correlation), 8.3 (pagination), 8.4 (timezone filter),
8.5/8.6 (ETag and optimistic locking).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from fastapi import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from trip_service.errors import trip_if_match_required, trip_validation_error, trip_version_mismatch
from trip_service.timezones import InvalidTimezoneError, calendar_date_range_to_utc

# ---------------------------------------------------------------------------
# V8 Section 8.2 — X-Request-Id Correlation
# Pure ASGI middleware — avoids BaseHTTPMiddleware asyncpg conflicts
# ---------------------------------------------------------------------------


class RequestIdMiddleware:
    """Ensure every request has an X-Request-Id and echo it in the response.

    Uses pure ASGI instead of BaseHTTPMiddleware to avoid the thread-wrapped
    call_next() that conflicts with asyncpg's connection model.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Extract or generate X-Request-Id
        headers = dict(scope.get("headers", []))
        request_id = headers.get(b"x-request-id", b"").decode() or str(uuid.uuid4())

        # Store in scope state for downstream access
        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["request_id"] = request_id

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                existing_headers = list(message.get("headers", []))
                existing_headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = existing_headers
            await send(message)

        await self.app(scope, receive, send_with_request_id)


# ---------------------------------------------------------------------------
# V8 Section 8.5 — ETag Utilities
# ---------------------------------------------------------------------------


def make_etag(trip_id: str, version: int) -> str:
    """Generate ETag string per V8 Section 16.1: '"trip-<trip_id>-v<version>"'."""
    return f'"trip-{trip_id}-v{version}"'


def parse_if_match(request: Request) -> tuple[str, int] | None:
    """Parse If-Match header. Returns (trip_id, version) or None if not present."""
    if_match = request.headers.get("if-match")
    if not if_match:
        return None
    # Strip surrounding quotes if present
    iv = if_match.strip()
    if iv.startswith('"') and iv.endswith('"') and len(iv) >= 2:
        raw = iv[1:-1]
    else:
        raw = iv
    match = re.match(r"^trip-(.+)-v(\d+)$", raw)
    if not match:
        return None
    return match.group(1), int(match.group(2))


def require_if_match(request: Request) -> tuple[str, int]:
    """Parse If-Match header or raise 428 per V8 Section 8.6."""
    result = parse_if_match(request)
    if result is None:
        raise trip_if_match_required()
    return result


def require_trip_if_match(request: Request, trip_id: str) -> int:
    """Parse If-Match header and ensure it belongs to the requested trip."""
    parsed_trip_id, version = require_if_match(request)
    if parsed_trip_id != trip_id:
        raise trip_version_mismatch()
    return version


# ---------------------------------------------------------------------------
# V8 Section 8.3 — Pagination Utilities
# ---------------------------------------------------------------------------


@dataclass
class PaginationParams:
    """Parsed and validated pagination parameters."""

    page: int
    per_page: int

    @property
    def offset(self) -> int:
        """SQL offset for current page."""
        return (self.page - 1) * self.per_page


def parse_pagination(page: int = 1, per_page: int = 50) -> PaginationParams:
    """Parse and clamp pagination params per V8 Section 8.3.

    - page is 1-based, minimum 1
    - per_page default 50, max 100
    """
    page = max(1, page)
    per_page = max(1, min(100, per_page))
    return PaginationParams(page=page, per_page=per_page)


def make_pagination_meta(
    page: int,
    per_page: int,
    total_items: int,
    sort: str = "trip_datetime_utc_desc,id_desc",
) -> dict[str, Any]:
    """Build the pagination meta object per V8 Section 8.3."""
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    return {
        "page": page,
        "per_page": per_page,
        "total_items": total_items,
        "total_pages": total_pages,
        "sort": sort,
    }


# ---------------------------------------------------------------------------
# V8 Section 8.4 — Timezone Date Filter
# ---------------------------------------------------------------------------


def date_range_to_utc(
    date_from: date | None,
    date_to: date | None,
    timezone: str = "Europe/Istanbul",
) -> tuple[datetime | None, datetime | None]:
    """Convert local calendar date range to UTC datetime window.

    V8 Section 8.4:
    - dates are interpreted as local calendar dates in the given timezone
    - date_to is inclusive at calendar-date level
    - returns [start_of_day UTC, next_day_start UTC)
    """
    try:
        return calendar_date_range_to_utc(date_from, date_to, timezone)
    except InvalidTimezoneError as exc:
        raise trip_validation_error(
            "Request validation failed.",
            errors=[{"field": "query.timezone", "message": "Invalid timezone."}],
        ) from exc


# ---------------------------------------------------------------------------
# V8 Section 18.2 — Prometheus Request Duration
# ---------------------------------------------------------------------------


class PrometheusMiddleware:
    """Measure HTTP request duration and record to Prometheus metrics."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        import time

        from trip_service.observability import REQUEST_DURATION

        start_time = time.perf_counter()
        method = scope["method"]
        path = scope["path"]

        # To avoid high cardinality, we usually map the path to a template
        # but for simplicity we'll use the path directly if it's low cardinality
        # In a real app, we'd use something like scope["route"].path

        status_code = [500]  # Default if send fails

        async def wrapped_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_code[0] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        finally:
            duration = time.perf_counter() - start_time
            # Standard labels: method, endpoint, status_code
            REQUEST_DURATION.labels(
                method=method,
                endpoint=path,
                status_code=status_code[0],
            ).observe(duration)
