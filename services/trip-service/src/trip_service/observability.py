"""Cleanup jobs and structured logging — V8 Sections 18, 19.

Phase 5 scope:
- Idempotency record cleanup (expired records)
- Outbox cleanup (PUBLISHED after 30 days, DEAD_LETTER after 90 days)
- Structured JSON logging setup
- Prometheus metrics registration
"""

from __future__ import annotations

import asyncio
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from prometheus_client import Counter, Histogram, Info
from sqlalchemy import CursorResult, delete
from sqlalchemy.exc import DBAPIError

from trip_service.config import settings
from trip_service.database import async_session_factory
from platform_common import OutboxPublishStatus
from trip_service.models import TripIdempotencyRecord, TripOutbox
from trip_service.worker_heartbeats import record_worker_heartbeat

logger = logging.getLogger("trip_service.cleanup")

# Correlation ContextVar for cross-service tracing propagation
correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


# ---------------------------------------------------------------------------
# V8 Section 18.1 — Structured Logging
# ---------------------------------------------------------------------------


def setup_logging(level: str = "INFO") -> None:
    """Configure structured JSON logging per V8 Section 18.1.

    Required fields: timestamp, level, service, request_id, message.
    """
    import json as json_mod

    class JsonFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            # Prioritize ContextVar, fallback to record attribute, then None
            c_id = (
                correlation_id.get() or getattr(record, "correlation_id", None) or getattr(record, "request_id", None)
            )

            log_entry = {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": record.levelname,
                "service": settings.service_name,
                "version": settings.service_version,
                "env": settings.environment,
                "logger": record.name,
                "message": record.getMessage(),
            }
            if c_id:
                log_entry["correlation_id"] = c_id
            if record.exc_info:
                log_entry["exception"] = self.formatException(record.exc_info)
            # Propagate extra fields (e.g. request_id) into the JSON output
            _standard_attrs = logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
            for key, value in record.__dict__.items():
                if key not in _standard_attrs and key not in log_entry:
                    log_entry[key] = value
            return json_mod.dumps(log_entry)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))


# ---------------------------------------------------------------------------
# V8 Section 18.2 — Prometheus Metrics
# ---------------------------------------------------------------------------

# Core Prometheus counters per V8 Section 18.2 (Standardized per TASK-0047)

METRICS_LABELS = ["service", "env", "version"]

TRIP_CREATED_TOTAL = Counter("trip_created_total", "Total trips created", METRICS_LABELS + ["source_type"])
TRIP_COMPLETED_TOTAL = Counter("trip_completed_total", "Total trips completed (approved)", METRICS_LABELS)
TRIP_CANCELLED_TOTAL = Counter("trip_cancelled_total", "Total trips cancelled (soft deleted)", METRICS_LABELS)
TRIP_HARD_DELETED_TOTAL = Counter("trip_hard_deleted_total", "Total trips hard deleted", METRICS_LABELS)
ENRICHMENT_CLAIMED_TOTAL = Counter("enrichment_claimed_total", "Enrichment rows claimed by workers", METRICS_LABELS)
ENRICHMENT_COMPLETED_TOTAL = Counter(
    "enrichment_completed_total", "Enrichment rows completed", METRICS_LABELS + ["result"]
)
ENRICHMENT_FAILED_TOTAL = Counter("enrichment_failed_total", "Enrichment rows that reached max retries", METRICS_LABELS)
OUTBOX_PUBLISHED_TOTAL = Counter(
    "trip_outbox_published_total", "Outbox events published", METRICS_LABELS + ["event_name"]
)
OUTBOX_DEAD_LETTER_TOTAL = Counter(
    "trip_outbox_dead_letter_total", "Outbox events that reached DEAD_LETTER", METRICS_LABELS
)
REQUEST_DURATION = Histogram(
    "trip_http_request_duration_seconds",
    "HTTP request duration",
    METRICS_LABELS + ["method", "endpoint", "status_code"],
)
HTTP_REQUESTS_TOTAL = Counter(
    "trip_http_requests_total",
    "Total number of HTTP requests",
    METRICS_LABELS + ["method", "endpoint", "status_code"],
)

TRIP_CB_STATE_CHANGES_TOTAL = Counter(
    "trip_cb_state_changes_total",
    "Total circuit breaker state changes",
    METRICS_LABELS + ["breaker_name", "state"],
)


SERVICE_INFO = Info("trip_service", "Trip Service version info")
SERVICE_INFO.info({"version": settings.service_version, "service": settings.service_name, "env": settings.environment})


def get_standard_labels() -> dict[str, str]:
    """Return the standard metadata labels for Prometheus metrics."""
    return {
        "service": settings.service_name,
        "env": settings.environment,
        "version": settings.service_version,
    }


# ---------------------------------------------------------------------------
# Cleanup Jobs
# ---------------------------------------------------------------------------


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _is_schema_not_ready(exc: Exception) -> bool:
    """Return whether a DB error means cleanup ran before migrations completed."""
    if not isinstance(exc, DBAPIError):
        return False
    message = str(exc).lower()
    return any(table in message for table in ("trip_idempotency_records", "trip_outbox")) and any(
        marker in message for marker in ("does not exist", "undefined table", "relation")
    )


async def cleanup_idempotency_records() -> int:
    """Delete expired idempotency records.

    V8 Section 15: 24-hour retention (configurable).
    Phase 2 writes the records; this job only handles cleanup.
    """
    now = _now_utc()

    async with async_session_factory() as session:
        stmt = delete(TripIdempotencyRecord).where(TripIdempotencyRecord.expires_at_utc < now)
        result = await session.execute(stmt)
        deleted = int(cast(CursorResult[Any], result).rowcount)
        await session.commit()

    if deleted > 0:
        logger.info("Cleaned up %d expired idempotency records", deleted)
    return deleted


async def cleanup_outbox_records() -> int:
    """Delete old outbox records per retention policy.

    - PUBLISHED: retained 30 days, then deleted
    - DEAD_LETTER: retained 90 days, then deleted
    """
    now = _now_utc()
    total_deleted = 0

    async with async_session_factory() as session:
        # PUBLISHED older than 30 days
        published_cutoff = now - timedelta(days=30)
        stmt1 = delete(TripOutbox).where(
            TripOutbox.publish_status == OutboxPublishStatus.PUBLISHED,
            TripOutbox.published_at_utc < published_cutoff,
        )
        result1 = await session.execute(stmt1)
        total_deleted += int(cast(CursorResult[Any], result1).rowcount)

        # DEAD_LETTER older than 90 days
        dl_cutoff = now - timedelta(days=90)
        stmt2 = delete(TripOutbox).where(
            TripOutbox.publish_status == OutboxPublishStatus.DEAD_LETTER,
            TripOutbox.created_at_utc < dl_cutoff,
        )
        result2 = await session.execute(stmt2)
        total_deleted += int(cast(CursorResult[Any], result2).rowcount)

        await session.commit()

    if total_deleted > 0:
        logger.info("Cleaned up %d outbox records", total_deleted)
    return total_deleted


async def run_cleanup_loop(
    interval_seconds: int = 3600,
    shutdown_event: asyncio.Event | None = None,
) -> None:
    """Run cleanup jobs periodically (default: every hour)."""
    worker_name = "cleanup-worker"
    logger.info("Cleanup loop starting (interval: %ds)", interval_seconds)

    while not (shutdown_event and shutdown_event.is_set()):
        try:
            await cleanup_idempotency_records()
            await cleanup_outbox_records()
            await record_worker_heartbeat(worker_name)
        except Exception as e:
            if _is_schema_not_ready(e):
                logger.warning("Cleanup skipped because the trip schema is not migrated yet")
            else:
                logger.error("Cleanup error: %s", e)

        await _sleep_with_heartbeats(worker_name, interval_seconds, shutdown_event)

    logger.info("Cleanup loop received shutdown signal, exiting.")


async def _sleep_with_heartbeats(
    worker_name: str,
    interval_seconds: int,
    shutdown_event: asyncio.Event | None = None,
) -> None:
    """Keep long-sleep workers healthy for readiness checks."""
    heartbeat_interval = max(1, min(settings.worker_heartbeat_timeout_seconds // 2, interval_seconds))
    remaining = interval_seconds

    while remaining > 0 and not (shutdown_event and shutdown_event.is_set()):
        await record_worker_heartbeat(worker_name)
        sleep_for = min(heartbeat_interval, remaining)
        try:
            if shutdown_event:
                await asyncio.wait_for(shutdown_event.wait(), timeout=sleep_for)
                return  # shutdown signalled
            else:
                await asyncio.sleep(sleep_for)
        except asyncio.TimeoutError:
            pass
        remaining -= sleep_for
