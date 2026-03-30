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
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from prometheus_client import Counter, Histogram, Info
from sqlalchemy import CursorResult, delete
from sqlalchemy.exc import DBAPIError

from trip_service.config import settings
from trip_service.database import async_session_factory
from trip_service.enums import OutboxPublishStatus
from trip_service.models import TripIdempotencyRecord, TripOutbox
from trip_service.worker_heartbeats import record_worker_heartbeat

logger = logging.getLogger("trip_service.cleanup")


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
            log_entry = {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": record.levelname,
                "service": settings.service_name,
                "logger": record.name,
                "message": record.getMessage(),
            }
            if hasattr(record, "request_id"):
                log_entry["request_id"] = record.request_id
            if record.exc_info:
                log_entry["exception"] = self.formatException(record.exc_info)
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

# Core Prometheus counters per V8 Section 18.2

TRIP_CREATED_TOTAL = Counter("trip_created_total", "Total trips created", ["source_type"])
TRIP_COMPLETED_TOTAL = Counter("trip_completed_total", "Total trips completed (approved)")
TRIP_CANCELLED_TOTAL = Counter("trip_cancelled_total", "Total trips cancelled (soft deleted)")
TRIP_HARD_DELETED_TOTAL = Counter("trip_hard_deleted_total", "Total trips hard deleted")
ENRICHMENT_CLAIMED_TOTAL = Counter("enrichment_claimed_total", "Enrichment rows claimed by workers")
ENRICHMENT_COMPLETED_TOTAL = Counter("enrichment_completed_total", "Enrichment rows completed", ["result"])
ENRICHMENT_FAILED_TOTAL = Counter("enrichment_failed_total", "Enrichment rows that reached max retries")
OUTBOX_PUBLISHED_TOTAL = Counter("outbox_published_total", "Outbox events published", ["event_name"])
OUTBOX_DEAD_LETTER_TOTAL = Counter("outbox_dead_letter_total", "Outbox events that reached DEAD_LETTER")
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration",
    ["method", "endpoint", "status_code"],
)

SERVICE_INFO = Info("trip_service", "Trip Service version info")
SERVICE_INFO.info({"version": "0.1.0", "service": settings.service_name})


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
    return (
        any(table in message for table in ("trip_idempotency_records", "trip_outbox"))
        and any(marker in message for marker in ("does not exist", "undefined table", "relation"))
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


async def run_cleanup_loop(interval_seconds: int = 3600) -> None:
    """Run cleanup jobs periodically (default: every hour)."""
    worker_name = "cleanup-worker"
    logger.info("Cleanup loop starting (interval: %ds)", interval_seconds)

    while True:
        try:
            await cleanup_idempotency_records()
            await cleanup_outbox_records()
            record_worker_heartbeat(worker_name)
        except Exception as e:
            if _is_schema_not_ready(e):
                logger.warning("Cleanup skipped because the trip schema is not migrated yet")
            else:
                logger.error("Cleanup error: %s", e)

        await _sleep_with_heartbeats(worker_name, interval_seconds)


async def _sleep_with_heartbeats(worker_name: str, interval_seconds: int) -> None:
    """Keep long-sleep workers healthy for readiness checks."""
    heartbeat_interval = max(1, min(settings.worker_heartbeat_timeout_seconds // 2, interval_seconds))
    remaining = interval_seconds

    while remaining > 0:
        record_worker_heartbeat(worker_name)
        sleep_for = min(heartbeat_interval, remaining)
        await asyncio.sleep(sleep_for)
        remaining -= sleep_for
