"""Request middleware: request ID propagation and Prometheus metrics."""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from fleet_service.observability import HTTP_REQUEST_DURATION_SECONDS, HTTP_REQUESTS_TOTAL


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a unique request_id and correlation_id to every request for structured logging."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Attach request_id and correlation_id from headers or generate them."""
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        correlation_id = request.headers.get("X-Correlation-Id") or request_id
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Correlation-Id"] = correlation_id
        return response


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Lightweight request timing middleware for observability."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Track request start time for latency metrics."""
        start_time = time.monotonic()
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            status_code = 500
            raise
        finally:
            duration = time.monotonic() - start_time
            method = request.method
            endpoint = request.url.path

            HTTP_REQUEST_DURATION_SECONDS.labels(method=method, endpoint=endpoint).observe(duration)
            HTTP_REQUESTS_TOTAL.labels(method=method, endpoint=endpoint, status_code=status_code).inc()

        return response
