"""Request middleware: request ID propagation and Prometheus metrics."""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from driver_service.observability import REQUEST_DURATION, correlation_id, get_standard_labels


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a unique request_id to every request for structured logging and error responses."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Attach correlation_id from header or generate one."""
        correlation_id_val = (
            request.headers.get("X-Correlation-ID") or request.headers.get("X-Request-Id") or str(uuid.uuid4())
        )
        request.state.correlation_id = correlation_id_val
        # Legacy support
        request.state.request_id = correlation_id_val

        # Set ContextVar for automated propagation and logging
        token = correlation_id.set(correlation_id_val)
        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = correlation_id_val
            return response
        finally:
            correlation_id.reset(token)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Lightweight request timing middleware for observability."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Track request start time for latency metrics."""
        start_time = time.perf_counter()
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            status_code = 500
            raise
        finally:
            duration = time.perf_counter() - start_time
            method = request.method
            endpoint = request.url.path
            labels = get_standard_labels()

            REQUEST_DURATION.labels(
                method=method,
                endpoint=endpoint,
                status_code=status_code,
                **labels,
            ).observe(duration)

        return response
