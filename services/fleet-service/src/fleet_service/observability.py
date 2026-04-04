"""Prometheus metrics and structured logging for Fleet Service (Section 16)."""

from __future__ import annotations

import json
import logging
import sys

from prometheus_client import Counter, Histogram

# --- HTTP metrics ---
HTTP_REQUESTS_TOTAL = Counter(
    "fleet_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "fleet_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
)

# --- Business metrics (Section 16.4) ---
VEHICLE_CREATE_TOTAL = Counter("fleet_vehicle_create_total", "Vehicle create operations")
VEHICLE_UPDATE_TOTAL = Counter("fleet_vehicle_update_total", "Vehicle update (PATCH) operations")
VEHICLE_DEACTIVATE_TOTAL = Counter("fleet_vehicle_deactivate_total", "Vehicle deactivate operations")
VEHICLE_REACTIVATE_TOTAL = Counter("fleet_vehicle_reactivate_total", "Vehicle reactivate operations")
VEHICLE_SOFT_DELETE_TOTAL = Counter("fleet_vehicle_soft_delete_total", "Vehicle soft-delete operations")
VEHICLE_HARD_DELETE_ATTEMPT_TOTAL = Counter("fleet_vehicle_hard_delete_attempt_total", "Vehicle hard-delete attempts")
VEHICLE_HARD_DELETE_REJECTED_TOTAL = Counter(
    "fleet_vehicle_hard_delete_rejected_total",
    "Vehicle hard-delete rejections",
    ["reject_stage", "reject_reason"],
)
VEHICLE_SPEC_VERSION_CREATE_TOTAL = Counter("fleet_vehicle_spec_version_create_total", "Vehicle spec version creations")

TRAILER_CREATE_TOTAL = Counter("fleet_trailer_create_total", "Trailer create operations")
TRAILER_UPDATE_TOTAL = Counter("fleet_trailer_update_total", "Trailer update (PATCH) operations")
TRAILER_DEACTIVATE_TOTAL = Counter("fleet_trailer_deactivate_total", "Trailer deactivate operations")
TRAILER_REACTIVATE_TOTAL = Counter("fleet_trailer_reactivate_total", "Trailer reactivate operations")
TRAILER_SOFT_DELETE_TOTAL = Counter("fleet_trailer_soft_delete_total", "Trailer soft-delete operations")
TRAILER_HARD_DELETE_ATTEMPT_TOTAL = Counter("fleet_trailer_hard_delete_attempt_total", "Trailer hard-delete attempts")
TRAILER_HARD_DELETE_REJECTED_TOTAL = Counter(
    "fleet_trailer_hard_delete_rejected_total",
    "Trailer hard-delete rejections",
    ["reject_stage", "reject_reason"],
)
TRAILER_SPEC_VERSION_CREATE_TOTAL = Counter("fleet_trailer_spec_version_create_total", "Trailer spec version creations")

VALIDATION_REQUESTS_TOTAL = Counter("fleet_validation_requests_total", "Validation requests", ["aggregate_type"])
VALIDATION_FAILURES_TOTAL = Counter(
    "fleet_validation_failures_total", "Validation failures", ["aggregate_type", "reason_code"]
)
SELECTABLE_QUERY_TOTAL = Counter("fleet_selectable_query_total", "Selectable queries", ["aggregate_type"])

OUTBOX_PUBLISH_SUCCESS_TOTAL = Counter("fleet_outbox_publish_success_total", "Outbox publish successes")
OUTBOX_PUBLISH_FAILURES_TOTAL = Counter("fleet_outbox_publish_failures_total", "Outbox publish failures")
OUTBOX_DEAD_LETTER_TOTAL = Counter("fleet_outbox_dead_letter_total", "Outbox dead letter entries")

DEPENDENCY_DRIVER_TIMEOUT_TOTAL = Counter("fleet_dependency_driver_timeout_total", "Driver Service timeouts")
DEPENDENCY_TRIP_TIMEOUT_TOTAL = Counter("fleet_dependency_trip_timeout_total", "Trip Service timeouts")
HTTP_BREAKER_OPEN_TOTAL = Counter("fleet_http_breaker_open_total", "Circuit breaker open events", ["target"])

IDEMPOTENCY_REPLAY_TOTAL = Counter("fleet_idempotency_replay_total", "Idempotency replays")
IDEMPOTENCY_HASH_MISMATCH_TOTAL = Counter("fleet_idempotency_hash_mismatch_total", "Idempotency hash mismatches")

# --- Outbound HTTP metrics ---
HTTP_OUTBOUND_REQUESTS_TOTAL = Counter(
    "fleet_http_outbound_requests_total",
    "Outbound HTTP requests",
    ["target", "status_code"],
)
HTTP_OUTBOUND_LATENCY = Histogram(
    "fleet_http_outbound_latency_histogram",
    "Outbound HTTP latency",
    ["target"],
)
HTTP_OUTBOUND_TIMEOUT_TOTAL = Counter(
    "fleet_http_outbound_timeout_total",
    "Outbound HTTP timeouts",
    ["target"],
)


class StructuredJsonFormatter(logging.Formatter):
    """JSON log formatter with all required fields from Section 16.3."""

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as structured JSON."""
        log_entry = {
            "timestamp_utc": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S.%fZ"),
            "service_name": "fleet-service",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Add extra fields from record if present
        for field in (
            "environment",
            "request_id",
            "correlation_id",
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


def setup_structured_logging(level: int = logging.INFO) -> None:
    """Configure structured JSON logging for the application."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredJsonFormatter())

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    # Reduce noise from libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
