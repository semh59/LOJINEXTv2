"""Observability: structured logging and Prometheus metrics."""

import logging
import sys
from typing import Any

from prometheus_client import Counter, Histogram


class JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        import json

        log_entry: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "correlation_id", "pair_id", "run_id"):
            val = getattr(record, key, None)
            if val:
                log_entry[key] = val

        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """Configure structured JSON logging for the service."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


PROCESSING_RUNS_TOTAL = Counter(
    "location_processing_runs_total",
    "Total processing runs started",
    ["trigger_type"],
)

PROCESSING_RUN_DURATION = Histogram(
    "location_processing_run_duration_seconds",
    "Processing run end-to-end duration",
    ["trigger_type", "status"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600],
)

PROCESSING_RUN_FAILURES = Counter(
    "location_processing_run_failures_total",
    "Processing run failures",
    ["trigger_type", "failure_reason"],
)

PROVIDER_CALLS_TOTAL = Counter(
    "location_provider_calls_total",
    "Total provider API calls",
    ["provider", "endpoint"],
)

PROVIDER_CALL_DURATION = Histogram(
    "location_provider_call_duration_seconds",
    "Provider API call duration",
    ["provider", "endpoint"],
    buckets=[0.1, 0.5, 1, 2, 4, 8, 15],
)

PROVIDER_CALL_ERRORS = Counter(
    "location_provider_call_errors_total",
    "Provider API call errors",
    ["provider", "endpoint", "error_type"],
)

API_REQUESTS_TOTAL = Counter(
    "location_api_requests_total",
    "Total API requests",
    ["method", "endpoint", "status_code"],
)

RESOLVE_REQUESTS_TOTAL = Counter(
    "location_resolve_requests_total",
    "Total resolve endpoint requests",
    ["result"],
)

DISPLAY_REQUESTS_TOTAL = Counter(
    "location_display_requests_total",
    "Total display endpoint requests",
    ["lang"],
)

BULK_REFRESH_ITEMS_TOTAL = Counter(
    "location_bulk_refresh_items_total",
    "Total bulk refresh items processed",
    ["status"],
)

STUCK_RUNS_RECOVERED = Counter(
    "location_stuck_runs_recovered_total",
    "Total stuck runs recovered at startup",
)
