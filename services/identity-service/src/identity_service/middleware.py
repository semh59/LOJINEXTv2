"""Standard platform middleware for Identity Service."""

import time
from uuid import uuid4

from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

from identity_service.observability import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    correlation_id,
    get_standard_labels,
)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Middleware to ensure every request has an X-Correlation-ID."""

    async def dispatch(self, request: Request, call_next):
        correlation_id_val = (
            request.headers.get("X-Correlation-ID")
            or request.headers.get("X-Request-ID")
            or str(uuid4())
        )
        # Store in request state for easy access
        request.state.correlation_id = correlation_id_val
        request.state.request_id = correlation_id_val

        # Set ContextVar
        token = correlation_id.set(correlation_id_val)
        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = correlation_id_val
            return response
        finally:
            correlation_id.reset(token)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Middleware to collect Prometheus metrics."""

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/metrics":
            return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

        method = request.method
        endpoint = request.url.path

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            status_code = 500
            raise
        finally:
            process_time = time.perf_counter() - start_time
            labels = get_standard_labels()
            HTTP_REQUESTS_TOTAL.labels(
                method=method, endpoint=endpoint, http_status=status_code, **labels
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method, endpoint=endpoint, **labels
            ).observe(process_time)

        return response
