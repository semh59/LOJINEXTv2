"""Observability utilities for telegram-service."""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from prometheus_client import Counter, Histogram

from telegram_service.config import settings

# ContextVar to store the current correlation ID
correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")


def get_standard_labels() -> dict[str, str]:
    """Return standard Prometheus labels for all metrics."""
    return {
        "service": "telegram-service",
        "env": settings.environment,
        "version": settings.service_version,
    }


METRICS_LABELS = ["service", "env", "version"]


def get_correlation_id() -> str:
    """Return the current correlation ID from context."""
    return correlation_id.get()


def set_correlation_id(value: str) -> Any:
    """Set the correlation ID in context and return the token."""
    return correlation_id.set(value)


def reset_correlation_id(token: Any) -> None:
    """Reset the correlation ID context."""
    correlation_id.reset(token)


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON with correlation ID."""

    def format(self, record: logging.LogRecord) -> str:
        cid = get_correlation_id() or getattr(record, "correlation_id", None)

        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": "telegram-service",
            "env": settings.environment,
            "service_version": settings.service_version,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if cid:
            log_entry["correlation_id"] = cid

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def setup_logging(level: str = "INFO") -> None:
    """Configure structured JSON logging for the service."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    # Avoid duplicate logs if handlers already exist
    if not root_logger.handlers:
        root_logger.addHandler(handler)
        root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    else:
        root_logger.handlers[0].setFormatter(JsonFormatter())
        root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))


# --- Standard Platform Metrics ---

HTTP_REQUESTS_TOTAL = Counter(
    "telegram_http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status_code"] + METRICS_LABELS,
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "telegram_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"] + METRICS_LABELS,
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# --- Bot Specific Metrics ---

BOT_UPDATES_TOTAL = Counter(
    "telegram_bot_updates_total",
    "Total number of Telegram updates received",
    ["update_type"] + METRICS_LABELS,
)

BOT_COMMANDS_TOTAL = Counter(
    "telegram_bot_commands_total",
    "Total number of bot commands executed",
    ["command"] + METRICS_LABELS,
)

BOT_OCR_REQUESTS_TOTAL = Counter(
    "telegram_bot_ocr_requests_total",
    "Total number of OCR requests processed",
    ["status"] + METRICS_LABELS,  # status: success, failure
)

BOT_PDF_GENERATED_TOTAL = Counter(
    "telegram_bot_pdf_generated_total",
    "Total number of PDFs generated",
    METRICS_LABELS,
)
