"""Request middleware: request ID propagation and Prometheus metrics.

Pure ASGI implementations — avoids BaseHTTPMiddleware asyncpg hang under load.
"""

from __future__ import annotations

import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from driver_service.observability import REQUEST_DURATION, correlation_id, get_standard_labels


class RequestIdMiddleware:
    """Attach a unique request_id and correlation_id to every request for structured logging.

    Pure ASGI instead of BaseHTTPMiddleware to avoid the thread-wrapped call_next()
    that conflicts with asyncpg's connection model under load.
    """

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
            or str(uuid.uuid4())
        )

        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["correlation_id"] = correlation_id_val
        scope["state"]["request_id"] = correlation_id_val

        token = correlation_id.set(correlation_id_val)

        async def send_with_correlation_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                existing_headers = list(message.get("headers", []))
                existing_headers.append((b"X-Correlation-ID", correlation_id_val.encode()))
                existing_headers.append((b"X-Request-Id", correlation_id_val.encode()))
                message["headers"] = existing_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_correlation_id)
        finally:
            correlation_id.reset(token)


class PrometheusMiddleware:
    """Lightweight request timing middleware for observability."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

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
