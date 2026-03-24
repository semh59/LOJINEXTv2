"""Shared middleware for Location Service.

Implements correlation (X-Request-Id), ETag/row_version utilities,
cursor pagination helpers, and idempotency support.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from location_service.errors import if_match_required, point_version_mismatch

# ---------------------------------------------------------------------------
# X-Request-Id Correlation
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
# ETag Utilities — Section 3A (row_version based)
# ---------------------------------------------------------------------------


def make_etag(row_version: int) -> str:
    """Generate ETag string from row_version: '"<row_version>"'."""
    return f'"{row_version}"'


def parse_if_match(request: Request) -> int | None:
    """Parse If-Match header. Returns row_version or None if not present."""
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


def check_version_match(request: Request, current_version: int) -> None:
    """Verify If-Match version matches current version, or raise 412."""
    client_version = require_if_match(request)
    if client_version != current_version:
        raise point_version_mismatch()


# ---------------------------------------------------------------------------
# Cursor Pagination (Section 7 common rules)
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
    """Parse and clamp pagination params.

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


# ---------------------------------------------------------------------------
# Idempotency Key Utilities (Section 16)
# ---------------------------------------------------------------------------


def compute_payload_hash(payload: bytes) -> str:
    """Compute SHA-256 hex digest of request payload for idempotency checks.

    Returns empty string for payloads exceeding 64KB (overflow behavior per spec).
    """
    if len(payload) > 65536:
        return ""
    return hashlib.sha256(payload).hexdigest()
