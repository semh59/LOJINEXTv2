"""Observability layer: Structured logging and ContextVar tracing."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

from prometheus_client import Counter, Histogram

from auth_service.config import settings

# Correlation ContextVar for cross-service tracing propagation
correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        # Prioritize ContextVar, fallback to record attributes
        c_id = (
            correlation_id.get()
            or getattr(record, "correlation_id", None)
            or getattr(record, "request_id", None)
        )

        log_entry = {
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

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def setup_logging(level: str = "INFO") -> None:
    """Configure structured JSON logging."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))


# ---------------------------------------------------------------------------
# Prometheus Metrics (Standardized per TASK-0047)
# ---------------------------------------------------------------------------

METRICS_LABELS = ["service", "env", "version"]

# Standard HTTP metrics
HTTP_REQUESTS_TOTAL = Counter(
    "auth_http_requests_total",
    "Total number of HTTP requests",
    METRICS_LABELS + ["method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "auth_http_request_duration_seconds",
    "HTTP request latency in seconds",
    METRICS_LABELS + ["method", "endpoint"],
)

OUTBOX_PUBLISHED_TOTAL = Counter(
    "auth_outbox_published_total",
    "Outbox events published",
    METRICS_LABELS + ["event_name"],
)

OUTBOX_DEAD_LETTER_TOTAL = Counter(
    "auth_outbox_dead_letter_total",
    "Outbox events that reached DEAD_LETTER",
    METRICS_LABELS,
)


def get_standard_labels() -> dict[str, str]:
    """Return the standard metadata labels for Prometheus metrics."""
    return {
        "service": settings.service_name,
        "env": settings.environment,
        "version": settings.service_version,
    }
