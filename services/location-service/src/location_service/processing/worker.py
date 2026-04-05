"""Dedicated worker loop for draining queued route-processing runs."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import DBAPIError, ProgrammingError

from location_service.config import settings
from location_service.database import async_session_factory
from location_service.enums import RunStatus
from location_service.models import ProcessingRun
from location_service.observability import (
    PROCESSING_RUN_DURATION,
    PROCESSING_RUN_FAILURES,
    PROCESSING_RUNS_TOTAL,
)
from location_service.processing.pipeline import _process_route_pair, mark_processing_run_failed
from location_service.worker_heartbeats import record_worker_heartbeat

logger = logging.getLogger(__name__)

WORKER_NAME = "processing-worker"


@dataclass(frozen=True)
class ClaimedProcessingRun:
    """A processing run claimed for worker-side execution."""

    run_id: uuid.UUID
    pair_id: uuid.UUID
    trigger_type: str
    claim_token: str


def _worker_identity() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _claim_expired_or_stale(now: datetime):
    reclaim_cutoff = now - timedelta(minutes=settings.run_stuck_sla_minutes)
    return and_(
        ProcessingRun.run_status == RunStatus.RUNNING,
        or_(
            ProcessingRun.claim_expires_at_utc.is_(None),
            ProcessingRun.claim_expires_at_utc < now,
            ProcessingRun.started_at_utc < reclaim_cutoff,
        ),
    )


def _is_schema_not_ready(exc: Exception) -> bool:
    if isinstance(exc, ProgrammingError):
        message = str(exc).lower()
        return "processing_runs" in message and any(marker in message for marker in ("does not exist", "relation"))

    if isinstance(exc, DBAPIError):
        message = str(exc).lower()
        return "processing_runs" in message and any(
            marker in message for marker in ("does not exist", "undefined table", "relation")
        )

    return False


async def claim_next_processing_run(worker_name: str | None = None) -> ClaimedProcessingRun | None:
    """Claim the next queued or stale processing run."""
    now = _utcnow()
    claim_ttl = timedelta(seconds=settings.processing_claim_ttl_seconds)
    claimed_by = worker_name or _worker_identity()

    async with async_session_factory() as session:
        stmt = (
            select(ProcessingRun)
            .where(
                or_(
                    ProcessingRun.run_status == RunStatus.QUEUED,
                    _claim_expired_or_stale(now),
                ),
                ProcessingRun.attempt_no < settings.processing_max_attempts,
            )
            .order_by(ProcessingRun.created_at_utc.asc(), ProcessingRun.processing_run_id.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        run = (await session.execute(stmt)).scalar_one_or_none()
        if run is None:
            return None

        claim_token = str(uuid.uuid4())
        is_reclaim = run.run_status == RunStatus.RUNNING

        run.run_status = RunStatus.RUNNING
        run.claim_token = claim_token
        run.claim_expires_at_utc = now + claim_ttl
        run.claimed_by_worker = claimed_by
        run.started_at_utc = now
        run.completed_at_utc = None
        run.error_message = None
        if is_reclaim:
            run.attempt_no += 1
        elif run.attempt_no == 0:  # Safety for legacy data or different defaults
            run.attempt_no = 1

        await session.commit()

        return ClaimedProcessingRun(
            run_id=run.processing_run_id,
            pair_id=run.route_pair_id,
            trigger_type=str(run.trigger_type),
            claim_token=claim_token,
        )


async def process_claimed_run(claimed_run: ClaimedProcessingRun) -> None:
    """Execute a claimed processing run and persist terminal state."""
    PROCESSING_RUNS_TOTAL.labels(trigger_type=claimed_run.trigger_type).inc()
    started_at = time.perf_counter()
    status = "succeeded"

    try:
        await _process_route_pair(
            claimed_run.run_id,
            claimed_run.pair_id,
            claim_token=claimed_run.claim_token,
        )
    except Exception as exc:
        status = "failed"
        PROCESSING_RUN_FAILURES.labels(
            trigger_type=claimed_run.trigger_type,
            failure_reason=type(exc).__name__,
        ).inc()
        await mark_processing_run_failed(
            claimed_run.run_id,
            str(exc),
            claim_token=claimed_run.claim_token,
        )
        logger.error(
            "Processing failed for pair %s run %s: %s",
            claimed_run.pair_id,
            claimed_run.run_id,
            exc,
            exc_info=True,
        )
    finally:
        PROCESSING_RUN_DURATION.labels(
            trigger_type=claimed_run.trigger_type,
            status=status,
        ).observe(time.perf_counter() - started_at)


async def run_processing_worker(
    *,
    poll_interval_seconds: float | None = None,
    worker_name: str | None = None,
) -> None:
    """Continuously claim and process queued route runs."""
    interval = poll_interval_seconds or settings.processing_poll_interval_seconds
    claimed_by = worker_name or _worker_identity()

    logger.info(
        "Processing worker starting",
        extra={
            "worker_name": WORKER_NAME,
            "claimed_by": claimed_by,
            "poll_interval_seconds": interval,
        },
    )

    while True:
        try:
            await record_worker_heartbeat(WORKER_NAME)
            claimed_run = await claim_next_processing_run(worker_name=claimed_by)
            if claimed_run is None:
                await asyncio.sleep(interval)
                continue

            await process_claimed_run(claimed_run)
            await record_worker_heartbeat(WORKER_NAME)
        except asyncio.CancelledError:
            logger.info("Processing worker cancelled")
            raise
        except Exception as exc:
            if _is_schema_not_ready(exc):
                logger.warning("Processing worker skipped because the location schema is not migrated yet")
            else:
                logger.error("Processing worker loop error: %s", exc, exc_info=True)
            await asyncio.sleep(interval)
