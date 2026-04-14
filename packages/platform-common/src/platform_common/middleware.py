from __future__ import annotations

import re
import time
from uuid import uuid4
from typing import Any, Callable

from starlette.types import ASGIApp, Message, Receive, Scope, Send
from .context import correlation_id

class RequestIdMiddleware:
    """Ensure every request has a Correlation ID and echo it in headers."""
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        correlation_id_val = (
            headers.get(b"x-correlation-id", b"").decode()
            or headers.get(b"x-request-id", b"").decode()
            or str(uuid4())
        )

        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["correlation_id"] = correlation_id_val
        scope["state"]["request_id"] = correlation_id_val

        token = correlation_id.set(correlation_id_val)

        async def send_with_ids(message: Message) -> None:
            if message["type"] == "http.response.start":
                existing_headers = list(message.get("headers", []))
                existing_headers.append((b"X-Correlation-ID", correlation_id_val.encode()))
                existing_headers.append((b"X-Request-Id", correlation_id_val.encode()))
                message["headers"] = existing_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_ids)
        finally:
            correlation_id.reset(token)

class PrometheusMiddleware:
    """Measure HTTP request duration and record to Prometheus metrics."""
    def __init__(
        self, 
        app: ASGIApp, 
        requests_counter: Any, 
        duration_histogram: Any, 
        label_provider: Callable[[], dict[str, str]] = lambda: {}
    ) -> None:
        self.app = app
        self.requests_counter = requests_counter
        self.duration_histogram = duration_histogram
        self.label_provider = label_provider

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope["method"]
        endpoint = self._normalize_path(path)
        start_time = time.perf_counter()
        status_code = [500]

        async def wrapped_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_code[0] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        finally:
            duration = time.perf_counter() - start_time
            labels = self.label_provider()
            self.requests_counter.labels(
                method=method, endpoint=endpoint, status_code=status_code[0], **labels
            ).inc()
            self.duration_histogram.labels(
                method=method, endpoint=endpoint, **labels
            ).observe(duration)

    def _normalize_path(self, path: str) -> str:
        """Replace ULIDs, UUIDs and numeric IDs with placeholders."""
        # Replace ULIDs (26 chars, uppercase/alphanumeric)
        path = re.sub(r"/[0-9A-HJKMNP-TV-Z]{26}", "/{id}", path)
        # Replace UUIDs
        path = re.sub(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "/{uuid}", path)
        # Replace numeric IDs
        path = re.sub(r"/\d+", "/{id}", path)
        return path
