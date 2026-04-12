"""Enrichment worker — V8 Section 13.

Implements the claim-based enrichment processing with:
- Claim algorithm using SELECT ... FOR UPDATE SKIP LOCKED (Section 13.6)
- Orphaned claim recovery (RUNNING + expired claim_expires_at_utc)
- Route enrichment via Location Service (with geocoding fallback)
- data_quality_flag recomputation after enrichment
- Retry policy with backoff + jitter (Section 13.7)
- Final state derivation (Section 13.8)

CRITICAL: This worker's retry backoff (1m→5m→15m→60m→6h) is SEPARATE from
the outbox relay backoff (5s→10s→30s→60s→5min). They must never share config.
"""

from __future__ import annotations

import asyncio
import logging
import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import DBAPIError

from platform_common import compute_data_quality_flag
from trip_service.config import settings
from trip_service.database import async_session_factory
from trip_service.dependencies import fetch_trip_context, resolve_route_by_names
from trip_service.enums import (
    EnrichmentStatus,
    RouteStatus,
)
from trip_service.errors import ProblemDetailError
from trip_service.models import TripTrip, TripTripEnrichment, TripTripEvidence
from trip_service.observability import (
    ENRICHMENT_CLAIMED_TOTAL,
    ENRICHMENT_COMPLETED_TOTAL,
    ENRICHMENT_FAILED_TOTAL,
    get_standard_labels,
)
from trip_service.trip_helpers import apply_trip_context
from trip_service.worker_heartbeats import record_worker_heartbeat

logger = logging.getLogger("trip_service.enrichment_worker")

# ---------------------------------------------------------------------------
# V8 Section 13.7 — Enrichment retry backoff (NOT outbox backoff)
# ---------------------------------------------------------------------------

ENRICHMENT_BACKOFF_SECONDS: list[int] = [
    60,  # 1 minute
    300,  # 5 minutes
    900,  # 15 minutes
    3600,  # 60 minutes
    21600,  # 6 hours
]

JITTER_FACTOR: float = 0.20  # ±20%


def _enrichment_next_retry_at(attempt_count: int) -> datetime:
    """Calculate next retry time with backoff + jitter.

    V8 Section 13.7: backoff 1m→5m→15m→60m→6h, jitter ±20%.
    """
    idx = min(attempt_count, len(ENRICHMENT_BACKOFF_SECONDS) - 1)
    base_seconds = ENRICHMENT_BACKOFF_SECONDS[idx]
    jitter = base_seconds * JITTER_FACTOR * (2 * random.random() - 1)  # ±20%
    delay = max(1, base_seconds + jitter)
    return _now_utc() + timedelta(seconds=delay)


def _now_utc() -> datetime:
    """Current UTC timestamp."""
    return datetime.now(UTC)


def _is_schema_not_ready(exc: Exception) -> bool:
    """Return whether a DB error means the trip schema is not migrated yet."""
    if not isinstance(exc, DBAPIError):
        return False
    message = str(exc).lower()
    return any(table in message for table in ("trip_trip_enrichment", "trip_trips", "trip_trip_evidence")) and any(
        marker in message for marker in ("does not exist", "undefined table", "relation")
    )


# ---------------------------------------------------------------------------
# V8 Section 13.8 — Final enrichment status derivation
# ---------------------------------------------------------------------------


def _derive_final_enrichment_status(route_status: str) -> str:
    """Derive final enrichment_status from sub-statuses per V8 Section 13.8.

    Rules (priority order):
    - if terminal success -> READY
    - if intentionally bypassed (SKIPPED) -> SKIPPED
    - if PENDING -> PENDING
    - if FAILED -> FAILED
    """
    if route_status == RouteStatus.READY:
        return EnrichmentStatus.READY
    if route_status == RouteStatus.SKIPPED:
        return EnrichmentStatus.SKIPPED
    if route_status == RouteStatus.FAILED:
        return EnrichmentStatus.FAILED
    return EnrichmentStatus.PENDING


@dataclass(frozen=True)
class _EnrichmentContext:
    """Snapshot of enrichment inputs loaded in a short DB session."""

    enrichment_id: str
    trip_id: str
    source_type: str
    route_status: str
    route_already_set: bool
    ocr_confidence: float | None
    origin_name_raw: str | None
    destination_name_raw: str | None


# ---------------------------------------------------------------------------
# V8 Section 13.6 — Worker Claim Algorithm
# ---------------------------------------------------------------------------


async def _claim_and_process_batch(worker_id: str, batch_size: int = 10) -> int:
    """Claim and process a batch of enrichment rows.

    V8 Section 13.6 — Claim Algorithm:
    1. SELECT candidates WHERE:
       - enrichment_status IN (PENDING, FAILED)
       - OR (enrichment_status = RUNNING AND claim_expires_at_utc < now())
       - AND (next_retry_at_utc IS NULL OR next_retry_at_utc <= now())
    2. SELECT ... FOR UPDATE SKIP LOCKED
    3. Atomically set RUNNING + claim fields
    4. Call external services AFTER claim is persisted
    5. On finish: clear claim fields, update statuses

    Returns number of rows processed.
    """
    processed = 0
    now = _now_utc()

    async with async_session_factory() as session:
        # Step 1+2: Select candidates with FOR UPDATE SKIP LOCKED
        stmt = (
            select(TripTripEnrichment)
            .where(
                # V8 Section 13.6 — candidate conditions
                or_(
                    and_(
                        TripTripEnrichment.enrichment_status.in_(
                            [
                                EnrichmentStatus.PENDING,
                                EnrichmentStatus.FAILED,
                            ]
                        ),
                        TripTripEnrichment.enrichment_attempt_count < settings.enrichment_max_attempts,
                    ),
                    # CRITICAL: Recover orphaned claims from crashed workers
                    and_(
                        TripTripEnrichment.enrichment_status == EnrichmentStatus.RUNNING,
                        TripTripEnrichment.claim_expires_at_utc < now,
                        TripTripEnrichment.enrichment_attempt_count < settings.enrichment_max_attempts,
                    ),
                ),
                or_(
                    TripTripEnrichment.next_retry_at_utc.is_(None),
                    TripTripEnrichment.next_retry_at_utc <= now,
                ),
            )
            .with_for_update(skip_locked=True)
            .limit(batch_size)
        )
        result = await session.execute(stmt)
        enrichment_rows = result.scalars().all()

        if not enrichment_rows:
            return 0

        claim_token = str(uuid.uuid4())
        claim_ttl = timedelta(seconds=settings.enrichment_claim_ttl_seconds)

        labels = get_standard_labels()
        ENRICHMENT_CLAIMED_TOTAL.labels(**labels).inc(len(enrichment_rows))

        # Step 3: Atomically claim rows
        for enrichment in enrichment_rows:
            enrichment.enrichment_status = EnrichmentStatus.RUNNING
            enrichment.claim_token = claim_token
            enrichment.claim_expires_at_utc = now + claim_ttl
            enrichment.claimed_by_worker = worker_id
            enrichment.updated_at_utc = now

        await session.commit()

    # Step 4: Process each claimed row (external calls AFTER claim is persisted)
    for enrichment in enrichment_rows:
        await _process_single_enrichment(enrichment.trip_id, enrichment.id, claim_token, worker_id)
        processed += 1

    return processed


async def _load_enrichment_context(
    *,
    trip_id: str,
    enrichment_id: str,
    claim_token: str,
) -> _EnrichmentContext | None:
    """Load enrichment inputs in a short-lived DB session before HTTP calls."""
    async with async_session_factory() as session:
        stmt = select(TripTripEnrichment).where(
            TripTripEnrichment.id == enrichment_id,
            TripTripEnrichment.claim_token == claim_token,
        )
        enrichment = (await session.execute(stmt)).scalar_one_or_none()
        if enrichment is None:
            logger.warning("Enrichment %s: claim lost (token mismatch), skipping", enrichment_id)
            return None

        trip = (await session.execute(select(TripTrip).where(TripTrip.id == trip_id))).scalar_one_or_none()
        if trip is None:
            logger.warning("Enrichment %s: trip %s not found, skipping", enrichment_id, trip_id)
            return None

        evidence = (
            await session.execute(
                select(TripTripEvidence)
                .where(TripTripEvidence.trip_id == trip_id)
                .order_by(TripTripEvidence.created_at_utc.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        return _EnrichmentContext(
            enrichment_id=enrichment_id,
            trip_id=trip_id,
            source_type=trip.source_type,
            route_status=enrichment.route_status,
            route_already_set=trip.route_id is not None,
            ocr_confidence=evidence.ocr_confidence if evidence else None,
            origin_name_raw=evidence.origin_name_raw if evidence else None,
            destination_name_raw=evidence.destination_name_raw if evidence else None,
        )


async def _resolve_route_context(context: _EnrichmentContext) -> tuple[str, object | None, str | None]:
    """Resolve route+pair externally without holding a DB session."""
    if context.route_status != RouteStatus.PENDING:
        return context.route_status, None, None

    if not context.origin_name_raw or not context.destination_name_raw:
        return RouteStatus.FAILED, None, None

    try:
        route_id, status, pair_id = await _resolve_route(
            origin_name=context.origin_name_raw,
            destination_name=context.destination_name_raw,
        )
        if status != RouteStatus.READY:
            return status, None, None

        # Fetch full context for the worker.
        # Note: pair_id is guaranteed to be non-None if status is READY
        trip_context = await fetch_trip_context(pair_id, field_name="evidence.origin_name_raw")  # type: ignore[arg-type]
        return RouteStatus.READY, trip_context, None
    except ProblemDetailError as exc:
        if exc.status == 422:
            logger.info("Enrichment %s: route resolution skipped: %s", context.enrichment_id, exc.code)
            return RouteStatus.SKIPPED, None, None
        logger.warning(
            "Enrichment %s: route resolution failed with problem status=%s code=%s",
            context.enrichment_id,
            exc.status,
            exc.code,
        )
        return RouteStatus.FAILED, None, exc.code


# ---------------------------------------------------------------------------
# Test & Internal Helpers — V8 Regression Recovery
# ---------------------------------------------------------------------------


async def _resolve_route(origin_name: str, destination_name: str) -> tuple[str | None, str, str | None]:
    """Internal helper for route resolution used by tests.

    This helper is required by the test suite to intercept service calls.
    Returns (route_id, status, pair_id).
    """
    client = await get_worker_client()
    url = f"{settings.location_service_url}/internal/v1/routes/resolve"
    headers = await _location_service_headers()
    try:
        response = await client.post(
            url,
            json={"origin_name": origin_name, "destination_name": destination_name},
            headers=headers,
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("route_id"), RouteStatus.READY, data.get("route_pair_id")

        # BUSINESS_INVALID or Ambiguous
        if response.status_code in (404, 422):
            return None, RouteStatus.SKIPPED, None

        return None, RouteStatus.FAILED, None
    except Exception:
        return None, RouteStatus.FAILED, None


async def _location_service_headers() -> dict[str, str]:
    """Proxy for location service headers (used by workers/tests)."""
    from trip_service.dependencies import _location_service_headers as deps_headers

    return await deps_headers()


async def get_worker_client() -> httpx.AsyncClient:
    """Proxy for obtaining the shared HTTP client (used by workers/tests)."""
    from trip_service.http_clients import get_dependency_client

    return await get_dependency_client()


async def _mark_processing_error(*, trip_id: str, enrichment_id: str, claim_token: str, error_text: str) -> None:
    """Persist failed enrichment state and release claim after unexpected errors."""
    async with async_session_factory() as session:
        enrichment = (
            await session.execute(
                select(TripTripEnrichment).where(
                    TripTripEnrichment.id == enrichment_id,
                    TripTripEnrichment.claim_token == claim_token,
                )
            )
        ).scalar_one_or_none()
        if enrichment is None:
            return

        now = _now_utc()
        enrichment.enrichment_status = EnrichmentStatus.FAILED
        enrichment.claim_token = None
        enrichment.claim_expires_at_utc = None
        enrichment.claimed_by_worker = None
        enrichment.last_enrichment_error_code = error_text[:100]
        enrichment.updated_at_utc = now

        labels = get_standard_labels()
        if enrichment.enrichment_attempt_count < settings.enrichment_max_attempts:
            enrichment.next_retry_at_utc = _enrichment_next_retry_at(enrichment.enrichment_attempt_count)
        else:
            enrichment.next_retry_at_utc = None
            ENRICHMENT_FAILED_TOTAL.labels(**labels).inc()
        enrichment.enrichment_attempt_count += 1
        await session.commit()


async def _save_enrichment_result(
    *,
    context: _EnrichmentContext,
    claim_token: str,
    route_status: str,
    trip_context: object | None,
    error_code: str | None = None,
) -> None:
    """Persist route/enrichment result in a short DB session."""
    async with async_session_factory() as session:
        enrichment = (
            await session.execute(
                select(TripTripEnrichment).where(
                    TripTripEnrichment.id == context.enrichment_id,
                    TripTripEnrichment.claim_token == claim_token,
                )
            )
        ).scalar_one_or_none()
        if enrichment is None:
            logger.warning("Enrichment %s: claim lost before save, skipping", context.enrichment_id)
            return

        trip = (await session.execute(select(TripTrip).where(TripTrip.id == context.trip_id))).scalar_one_or_none()
        if trip is None:
            logger.warning("Enrichment %s: trip %s not found during save", context.enrichment_id, context.trip_id)
            return

        route_resolved = False
        if route_status == RouteStatus.READY:
            if trip_context is not None:
                apply_trip_context(trip, trip_context, reverse=False)
            route_resolved = trip.route_id is not None or context.route_already_set
        elif context.route_status == RouteStatus.READY and context.route_already_set:
            route_resolved = True

        now = _now_utc()
        enrichment.route_status = route_status
        enrichment.enrichment_status = _derive_final_enrichment_status(route_status)
        enrichment.data_quality_flag = compute_data_quality_flag(
            context.source_type,
            context.ocr_confidence,
            route_resolved=route_resolved,
        )
        enrichment.claim_token = None
        enrichment.claim_expires_at_utc = None
        enrichment.claimed_by_worker = None
        enrichment.last_enrichment_error_code = error_code[:100] if error_code else None
        enrichment.updated_at_utc = now

        labels = get_standard_labels()
        if enrichment.enrichment_status in (EnrichmentStatus.PENDING, EnrichmentStatus.FAILED):
            if enrichment.enrichment_attempt_count < settings.enrichment_max_attempts:
                enrichment.next_retry_at_utc = _enrichment_next_retry_at(enrichment.enrichment_attempt_count)
            else:
                enrichment.enrichment_status = EnrichmentStatus.FAILED
                enrichment.next_retry_at_utc = None
                ENRICHMENT_FAILED_TOTAL.labels(**labels).inc()
        else:
            enrichment.next_retry_at_utc = None
        enrichment.enrichment_attempt_count += 1

        await session.commit()
        ENRICHMENT_COMPLETED_TOTAL.labels(result=enrichment.enrichment_status, **labels).inc()

        logger.info(
            "Enrichment %s: completed — route=%s enrichment=%s quality=%s",
            context.enrichment_id,
            enrichment.route_status,
            enrichment.enrichment_status,
            enrichment.data_quality_flag,
        )


async def _process_single_enrichment(
    trip_id: str,
    enrichment_id: str,
    claim_token: str,
    worker_id: str,
) -> None:
    """Process a single enrichment row.

    Handles route resolution → final status derivation.
    """
    from trip_service.observability import correlation_id

    token = correlation_id.set(trip_id)
    try:
        _ = worker_id
        context = await _load_enrichment_context(trip_id=trip_id, enrichment_id=enrichment_id, claim_token=claim_token)
        if context is None:
            return

        route_status, trip_context, error_code = await _resolve_route_context(context)
        await _save_enrichment_result(
            context=context,
            claim_token=claim_token,
            route_status=route_status,
            trip_context=trip_context,
            error_code=error_code,
        )
    except Exception as exc:
        logger.error("Enrichment %s: processing error: %s", enrichment_id, exc)
        await _mark_processing_error(
            trip_id=trip_id,
            enrichment_id=enrichment_id,
            claim_token=claim_token,
            error_text=str(exc),
        )
    finally:
        correlation_id.reset(token)


# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------


async def run_enrichment_worker(
    worker_id: str | None = None,
    shutdown_event: asyncio.Event | None = None,
) -> None:
    """Main enrichment worker loop.

    Runs indefinitely, polling for work at configured intervals.
    Multiple instances are safe (claim locking).

    Args:
        worker_id: Unique identifier for this worker instance.
        shutdown_event: Optional asyncio.Event to signal graceful shutdown.
    """
    if worker_id is None:
        worker_id = f"worker-{uuid.uuid4().hex[:8]}"

    logger.info("Enrichment worker %s starting", worker_id)

    while not (shutdown_event and shutdown_event.is_set()):
        try:
            processed = await _claim_and_process_batch(worker_id)
            if processed > 0:
                logger.info("Worker %s: processed %d enrichment rows", worker_id, processed)
            await record_worker_heartbeat("enrichment-worker")
        except Exception as e:
            if _is_schema_not_ready(e):
                logger.warning("Worker %s: schema not migrated yet, skipping this interval", worker_id)
            else:
                logger.error("Worker %s: batch error: %s", worker_id, e)

        # Use wait_for instead of sleep so shutdown signal interrupts promptly
        if shutdown_event and shutdown_event.is_set():
            break
        try:
            await asyncio.wait_for(
                shutdown_event.wait() if shutdown_event else asyncio.sleep(settings.enrichment_poll_interval_seconds),
                timeout=settings.enrichment_poll_interval_seconds,
            )
            # If we reach here, event was set → exit
            break
        except asyncio.TimeoutError:
            # Normal timeout → continue polling
            pass

    logger.info("Enrichment worker %s shutting down gracefully", worker_id)
