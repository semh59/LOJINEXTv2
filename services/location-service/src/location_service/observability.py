"""Observability: structured logging and Prometheus metrics."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from prometheus_client import Counter, Histogram

from location_service.config import settings

# Correlation ContextVar for cross-service tracing propagation
correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def get_standard_labels() -> dict[str, str]:
    """Return standard Prometheus labels for all metrics."""
    return {
        "service": settings.service_name,
        "env": settings.environment,
        "version": settings.service_version,
    }


METRICS_LABELS = ["service", "env", "version"]


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        # Prioritize ContextVar, fallback to record attribute, then legacy/etc
        c_id = correlation_id.get() or getattr(record, "correlation_id", None) or getattr(record, "request_id", None)

        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": settings.service_name,
            "env": settings.environment,
            "service_version": settings.service_version,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if c_id:
            log_entry["correlation_id"] = c_id

        # Keep other possible business keys
        for key in ("pair_id", "run_id"):
            val = getattr(record, key, None)
            if val:
                log_entry[key] = val

        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """Configure structured JSON logging for the service."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


# --- Standardized API Metrics ---

REQUEST_DURATION = Histogram(
    "location_http_request_duration_seconds",
    "API request latency",
    ["method", "endpoint", "status_code"] + METRICS_LABELS,
)

HTTP_REQUESTS_TOTAL = Counter(
    "location_http_requests_total",
    "Total number of HTTP requests",
    METRICS_LABELS + ["method", "endpoint", "status_code"],
)

# --- Service Specific Metrics ---

PROCESSING_RUNS_TOTAL = Counter(
    "location_processing_runs_total",
    "Total processing runs started",
    ["trigger_type"] + METRICS_LABELS,
)

PROCESSING_RUN_DURATION = Histogram(
    "location_processing_run_duration_seconds",
    "Processing run end-to-end duration",
    ["trigger_type", "status"] + METRICS_LABELS,
    buckets=[1, 5, 10, 30, 60, 120, 300, 600],
)

PROCESSING_RUN_FAILURES = Counter(
    "location_processing_run_failures_total",
    "Processing run failures",
    ["trigger_type", "failure_reason"] + METRICS_LABELS,
)

PROVIDER_CALLS_TOTAL = Counter(
    "location_provider_calls_total",
    "Total provider API calls",
    ["provider", "endpoint"] + METRICS_LABELS,
)

PROVIDER_CALL_DURATION = Histogram(
    "location_provider_call_duration_seconds",
    "Provider API call duration",
    ["provider", "endpoint"] + METRICS_LABELS,
    buckets=[0.1, 0.5, 1, 2, 4, 8, 15],
)

PROVIDER_CALL_ERRORS = Counter(
    "location_provider_call_errors_total",
    "Provider API call errors",
    ["provider", "endpoint", "error_type"] + METRICS_LABELS,
)

RESOLVE_REQUESTS_TOTAL = Counter(
    "location_resolve_requests_total",
    "Total resolve endpoint requests",
    ["result"] + METRICS_LABELS,
)

DISPLAY_REQUESTS_TOTAL = Counter(
    "location_display_requests_total",
    "Total display endpoint requests",
    ["lang"] + METRICS_LABELS,
)

BULK_REFRESH_ITEMS_TOTAL = Counter(
    "location_bulk_refresh_items_total",
    "Total bulk refresh items processed",
    ["status"] + METRICS_LABELS,
)

OUTBOX_PUBLISHED_TOTAL = Counter(
    "location_outbox_published_total",
    "Outbox events published",
    METRICS_LABELS + ["event_name"],
)

OUTBOX_DEAD_LETTER_TOTAL = Counter(
    "location_outbox_dead_letter_total",
    "Outbox events that reached DEAD_LETTER",
    METRICS_LABELS,
)

STUCK_RUNS_RECOVERED = Counter(
    "location_stuck_runs_recovered_total",
    "Total stuck runs recovered at startup",
    METRICS_LABELS,
)

API_REQUESTS_TOTAL = REQUEST_DURATION
API_REQUEST_DURATION_SECONDS = REQUEST_DURATION
