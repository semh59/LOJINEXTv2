"""Standard platform middleware for Identity Service."""

import logging
import time
from uuid import uuid4

from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("identity_service")

# Metrics definitions
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "http_status"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Middleware to ensure every request has an X-Correlation-ID."""

    async def dispatch(self, request: Request, call_next):
        request_id = (
            request.headers.get("X-Correlation-ID")
            or request.headers.get("X-Request-ID")
            or str(uuid4())
        )
        # Store in request state for easy access
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Correlation-ID"] = request_id
        return response


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
            HTTP_REQUESTS_TOTAL.labels(
                method=method, endpoint=endpoint, http_status=status_code
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method, endpoint=endpoint
            ).observe(process_time)

        return response
