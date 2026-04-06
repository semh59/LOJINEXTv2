"""Observability layer: Structured logging and Prometheus metrics."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime


from prometheus_client import Counter, Histogram

from driver_service.config import settings

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


# ---------------------------------------------------------------------------
# STRUCTURED LOGGING
# ---------------------------------------------------------------------------


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        # Prioritize ContextVar, fallback to record attribute
        c_id = correlation_id.get() or getattr(record, "correlation_id", None) or getattr(record, "request_id", None)

        log_data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": settings.service_name,
            "env": settings.environment,
            "service_version": settings.service_version,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if c_id:
            log_data["correlation_id"] = c_id

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def setup_logging(level: int = logging.INFO) -> None:
    """Configure structured JSON logging."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

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
REQUEST_DURATION = Histogram(
    "driver_request_duration_seconds",
    "API request latency",
    ["method", "endpoint", "status_code"] + METRICS_LABELS,
)

# Outbox Worker Metrics
OUTBOX_EVENTS_PUBLISHED = Counter(
    "driver_outbox_events_published_total",
    "Total outgoing events published successfully",
    ["event_name"] + METRICS_LABELS,
)

OUTBOX_PUBLISH_FAILURES = Counter(
    "driver_outbox_publish_failures_total",
    "Total outbox relay failures to Kafka",
    ["event_name"] + METRICS_LABELS,
)

# Business Metrics
DRIVERS_CREATED_TOTAL = Counter(
    "driver_records_created_total",
    "Total number of drivers mathematically created in canonical store",
    METRICS_LABELS,
)

DRIVERS_SOFT_DELETED_TOTAL = Counter(
    "driver_records_soft_deleted_total",
    "Total number of drivers marked soft-deleted",
    METRICS_LABELS,
)

# --- Legacy Aliases ---
HTTP_REQUESTS_TOTAL = REQUEST_DURATION
HTTP_REQUEST_DURATION_SECONDS = REQUEST_DURATION
