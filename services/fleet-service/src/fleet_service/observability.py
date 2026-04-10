"""Prometheus metrics and structured logging for Fleet Service (Section 16)."""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

from prometheus_client import Counter, Histogram

from fleet_service.config import settings

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

# --- API metrics ---
REQUEST_DURATION = Histogram(
    "fleet_http_request_duration_seconds",
    "API request latency",
    ["method", "endpoint", "status_code"] + METRICS_LABELS,
)

HTTP_REQUESTS_TOTAL = Counter(
    "fleet_http_requests_total",
    "Total number of HTTP requests",
    METRICS_LABELS + ["method", "endpoint", "status_code"],
)

# --- Business metrics (Section 16.4) ---
VEHICLE_CREATE_TOTAL = Counter("fleet_vehicle_create_total", "Vehicle create operations", METRICS_LABELS)
VEHICLE_UPDATE_TOTAL = Counter("fleet_vehicle_update_total", "Vehicle update (PATCH) operations", METRICS_LABELS)
VEHICLE_DEACTIVATE_TOTAL = Counter("fleet_vehicle_deactivate_total", "Vehicle deactivate operations", METRICS_LABELS)
VEHICLE_REACTIVATE_TOTAL = Counter("fleet_vehicle_reactivate_total", "Vehicle reactivate operations", METRICS_LABELS)
VEHICLE_SOFT_DELETE_TOTAL = Counter("fleet_vehicle_soft_delete_total", "Vehicle soft-delete operations", METRICS_LABELS)
VEHICLE_HARD_DELETE_ATTEMPT_TOTAL = Counter(
    "fleet_vehicle_hard_delete_attempt_total", "Vehicle hard-delete attempts", METRICS_LABELS
)
VEHICLE_HARD_DELETE_REJECTED_TOTAL = Counter(
    "fleet_vehicle_hard_delete_rejected_total",
    "Vehicle hard-delete rejections",
    ["reject_stage", "reject_reason"] + METRICS_LABELS,
)
VEHICLE_SPEC_VERSION_CREATE_TOTAL = Counter(
    "fleet_vehicle_spec_version_create_total", "Vehicle spec version creations", METRICS_LABELS
)

TRAILER_CREATE_TOTAL = Counter("fleet_trailer_create_total", "Trailer create operations", METRICS_LABELS)
TRAILER_UPDATE_TOTAL = Counter("fleet_trailer_update_total", "Trailer update (PATCH) operations", METRICS_LABELS)
TRAILER_DEACTIVATE_TOTAL = Counter("fleet_trailer_deactivate_total", "Trailer deactivate operations", METRICS_LABELS)
TRAILER_REACTIVATE_TOTAL = Counter("fleet_trailer_reactivate_total", "Trailer reactivate operations", METRICS_LABELS)
TRAILER_SOFT_DELETE_TOTAL = Counter("fleet_trailer_soft_delete_total", "Trailer soft-delete operations", METRICS_LABELS)
TRAILER_HARD_DELETE_ATTEMPT_TOTAL = Counter(
    "fleet_trailer_hard_delete_attempt_total", "Trailer hard-delete attempts", METRICS_LABELS
)
TRAILER_HARD_DELETE_REJECTED_TOTAL = Counter(
    "fleet_trailer_hard_delete_rejected_total",
    "Trailer hard-delete rejections",
    ["reject_stage", "reject_reason"] + METRICS_LABELS,
)
TRAILER_SPEC_VERSION_CREATE_TOTAL = Counter(
    "fleet_trailer_spec_version_create_total", "Trailer spec version creations", METRICS_LABELS
)

VALIDATION_REQUESTS_TOTAL = Counter(
    "fleet_validation_requests_total", "Validation requests", ["aggregate_type"] + METRICS_LABELS
)
VALIDATION_FAILURES_TOTAL = Counter(
    "fleet_validation_failures_total", "Validation failures", ["aggregate_type", "reason_code"] + METRICS_LABELS
)
SELECTABLE_QUERY_TOTAL = Counter(
    "fleet_selectable_query_total", "Selectable queries", ["aggregate_type"] + METRICS_LABELS
)

OUTBOX_PUBLISH_SUCCESS_TOTAL = Counter("fleet_outbox_published_total", "Outbox publish successes", METRICS_LABELS)
OUTBOX_PUBLISH_FAILURES_TOTAL = Counter(
    "fleet_outbox_publish_failures_total", "Outbox publish failures", METRICS_LABELS
)
OUTBOX_DEAD_LETTER_TOTAL = Counter("fleet_outbox_dead_letter_total", "Outbox dead letter entries", METRICS_LABELS)

DEPENDENCY_DRIVER_TIMEOUT_TOTAL = Counter(
    "fleet_dependency_driver_timeout_total", "Driver Service timeouts", METRICS_LABELS
)
DEPENDENCY_TRIP_TIMEOUT_TOTAL = Counter("fleet_dependency_trip_timeout_total", "Trip Service timeouts", METRICS_LABELS)
HTTP_BREAKER_OPEN_TOTAL = Counter(
    "fleet_http_breaker_open_total", "Circuit breaker open events", ["target"] + METRICS_LABELS
)

IDEMPOTENCY_REPLAY_TOTAL = Counter("fleet_idempotency_replay_total", "Idempotency replays", METRICS_LABELS)
IDEMPOTENCY_HASH_MISMATCH_TOTAL = Counter(
    "fleet_idempotency_hash_mismatch_total", "Idempotency hash mismatches", METRICS_LABELS
)

# --- Outbound HTTP metrics ---
HTTP_OUTBOUND_REQUESTS_TOTAL = Counter(
    "fleet_http_outbound_requests_total",
    "Outbound HTTP requests",
    ["target", "status_code"] + METRICS_LABELS,
)
HTTP_OUTBOUND_LATENCY = Histogram(
    "fleet_http_outbound_latency_histogram",
    "Outbound HTTP latency",
    ["target"] + METRICS_LABELS,
)
HTTP_OUTBOUND_TIMEOUT_TOTAL = Counter(
    "fleet_http_outbound_timeout_total",
    "Outbound HTTP timeouts",
    ["target"] + METRICS_LABELS,
)

# --- Legacy Aliases ---
HTTP_REQUEST_DURATION_SECONDS = REQUEST_DURATION


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as structured JSON."""
        # Prioritize ContextVar, fallback to record attribute
        c_id = correlation_id.get() or getattr(record, "correlation_id", None) or getattr(record, "request_id", None)

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

        # Add extra business fields from record if present
        for field in (
            "actor_type",
            "actor_id",
            "aggregate_type",
            "aggregate_id",
            "action",
            "result",
            "error_code",
            "status_before",
            "status_after",
            "spec_version_before",
            "spec_version_after",
        ):
            value = getattr(record, field, None)
            if value is not None:
                log_entry[field] = value

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    """Configure structured JSON logging."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    # Reduce noise from libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
