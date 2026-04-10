"""Shared middleware for Location Service.

Implements correlation (X-Request-Id), ETag/row_version utilities,
cursor pagination helpers, and idempotency support.
"""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import Request, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from location_service.errors import ProblemDetailError, if_match_required, point_version_mismatch
from location_service.observability import correlation_id


class RequestIdMiddleware:
    """Ensure every request has an X-Request-Id and echo it in the response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Extract or generate X-Correlation-ID (case-insensitive extraction)
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        correlation_id_val = (
            headers.get(b"x-correlation-id", b"").decode()
            or headers.get(b"x-request-id", b"").decode()
            or str(uuid.uuid4())
        )

        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["correlation_id"] = correlation_id_val
        # Legacy support for internal code still using request_id
        scope["state"]["request_id"] = correlation_id_val

        # Set ContextVar for automated propagation and logging
        token = correlation_id.set(correlation_id_val)

        async def send_with_correlation_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                existing_headers = list(message.get("headers", []))
                # Inject standard X-Correlation-ID (standard case)
                existing_headers.append((b"X-Correlation-ID", correlation_id_val.encode()))
                existing_headers.append((b"X-Request-Id", correlation_id_val.encode()))
                message["headers"] = existing_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_correlation_id)
        finally:
            correlation_id.reset(token)


class PrometheusMiddleware:
    """Pure ASGI middleware that records request counters and latency."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        from location_service.observability import REQUEST_DURATION, get_standard_labels

        start_time = time.perf_counter()
        method = scope["method"]
        path = scope["path"]
        status_code = [500]

        async def wrapped_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_code[0] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        finally:
            duration = time.perf_counter() - start_time
            labels = get_standard_labels()
            REQUEST_DURATION.labels(
                method=method,
                endpoint=path,
                status_code=status_code[0],
                **labels,
            ).observe(duration)


def make_etag(row_version: int) -> str:
    """Generate ETag string from row_version."""
    return f'"{row_version}"'


def set_etag(response: Response, row_version: int) -> None:
    """Attach the standard ETag header for a row-versioned resource."""
    response.headers["ETag"] = make_etag(row_version)


def parse_if_match(request: Request) -> int | None:
    """Parse the If-Match header and return a row version if present."""
    if_match = request.headers.get("if-match")
    if not if_match:
        return None
    raw = if_match.strip().strip('"')
    match = re.match(r"^(\d+)$", raw)
    if not match:
        return None
    return int(match.group(1))


def require_if_match(request: Request) -> int:
    """Parse If-Match header or raise 428."""
    result = parse_if_match(request)
    if result is None:
        raise if_match_required()
    return result


def check_version_match(
    request: Request,
    current_version: int,
    mismatch_factory: Callable[[], ProblemDetailError] = point_version_mismatch,
) -> None:
    """Verify If-Match version matches current version, or raise 412."""
    client_version = require_if_match(request)
    if client_version != current_version:
        raise mismatch_factory()


@dataclass
class PaginationParams:
    """Parsed and validated pagination parameters."""

    page: int
    per_page: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page


def parse_pagination(page: int = 1, per_page: int = 50) -> PaginationParams:
    """Parse and clamp pagination params."""
    page = max(1, page)
    per_page = max(1, min(100, per_page))
    return PaginationParams(page=page, per_page=per_page)


def make_pagination_meta(
    page: int,
    per_page: int,
    total_items: int,
    sort: str = "created_at_utc_desc,id_desc",
) -> dict[str, Any]:
    """Build the pagination meta object."""
    total_pages = max(1, (total_items + per_page - 1) // per_page) if total_items > 0 else 0
    return {
        "page": page,
        "per_page": per_page,
        "total_items": total_items,
        "total_pages": total_pages,
        "sort": sort,
    }


def compute_payload_hash(payload: bytes) -> str:
    """Compute SHA-256 hex digest of request payload for idempotency checks."""
    if len(payload) > 65536:
        return ""
    return hashlib.sha256(payload).hexdigest()
