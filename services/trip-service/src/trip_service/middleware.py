"""Shared middleware for Trip Service.

Implements V8 Sections 8.2 (correlation), 8.3 (pagination), 8.4 (timezone filter),
8.5/8.6 (ETag and optimistic locking).
"""

from __future__ import annotations

from platform_common import PrometheusMiddleware, RequestIdMiddleware

from trip_service.errors import trip_if_match_required, trip_validation_error

__all__ = [
    "RequestIdMiddleware",
    "PrometheusMiddleware",
    "trip_if_match_required",
    "trip_validation_error",
]
