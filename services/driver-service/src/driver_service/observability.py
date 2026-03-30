"""Observability layer: Structured logging and Prometheus metrics."""

import logging
import sys

from prometheus_client import Counter, Histogram

# ---------------------------------------------------------------------------
# STRUCTURED LOGGING
# ---------------------------------------------------------------------------


class StructuredFormatter(logging.Formatter):
    """Simple JSON-like structured formatter for core service logs."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        import json

        return json.dumps(log_data)


def setup_structured_logging(level: int = logging.INFO) -> None:
    """Configure python logging to use structured JSON."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers explicitly to avoid duplicate logs
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)

    root_logger.addHandler(handler)


# ---------------------------------------------------------------------------
# PROMETHEUS METRICS
# ---------------------------------------------------------------------------

# HTTP Request Metrics
HTTP_REQUESTS_TOTAL = Counter(
    "driver_http_requests_total",
    "Total number of HTTP requests processed",
    ["method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "driver_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Outbox Worker Metrics
OUTBOX_EVENTS_PUBLISHED = Counter(
    "driver_outbox_events_published_total",
    "Total outgoing events published successfully",
    ["event_name"],
)

OUTBOX_PUBLISH_FAILURES = Counter(
    "driver_outbox_publish_failures_total",
    "Total outbox relay failures to RabbitMQ",
    ["event_name"],
)

# Business Metrics
DRIVERS_CREATED_TOTAL = Counter(
    "driver_records_created_total",
    "Total number of drivers mathematically created in canonical store",
)

DRIVERS_SOFT_DELETED_TOTAL = Counter(
    "driver_records_soft_deleted_total",
    "Total number of drivers marked soft-deleted",
)
