import time
from uuid import uuid4

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from telegram_service.observability import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    correlation_id,
    get_standard_labels,
)


class RequestIdMiddleware:
    """Pure ASGI middleware to ensure every request has an X-Correlation-ID."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        correlation_id_val = None
        for key, value in scope["headers"]:
            if key in (b"x-correlation-id", b"x-request-id"):
                correlation_id_val = value.decode("latin-1")
                break

        if not correlation_id_val:
            correlation_id_val = str(uuid4())

        # Set ContextVar
        token = correlation_id.set(correlation_id_val)

        async def send_wrapper(message: dict):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"X-Correlation-ID", correlation_id_val.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            correlation_id.reset(token)


class PrometheusMiddleware:
    """Pure ASGI middleware to collect Prometheus metrics and expose /metrics."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        if path == "/metrics":
            response = Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
            await response(scope, receive, send)
            return

        method = scope["method"]
        start_time = time.perf_counter()
        status_code = [500]  # Use list for mutability in closure

        async def send_wrapper(message: dict):
            if message["type"] == "http.response.start":
                status_code[0] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            process_time = time.perf_counter() - start_time
            labels = get_standard_labels()
            HTTP_REQUESTS_TOTAL.labels(method=method, endpoint=path, status_code=status_code[0], **labels).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(method=method, endpoint=path, **labels).observe(process_time)
