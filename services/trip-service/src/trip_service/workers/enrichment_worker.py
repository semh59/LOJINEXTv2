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
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import DBAPIError

from trip_service.config import settings
from trip_service.database import async_session_factory
from trip_service.dependencies import _location_service_headers, _problem_code
from trip_service.enums import (
    DataQualityFlag,
    EnrichmentStatus,
    RouteStatus,
    SourceType,
)
from trip_service.http_clients import get_worker_client
from trip_service.models import TripTrip, TripTripEnrichment, TripTripEvidence
from trip_service.observability import ENRICHMENT_CLAIMED_TOTAL, ENRICHMENT_COMPLETED_TOTAL, ENRICHMENT_FAILED_TOTAL
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
# V8 Section 6.3 — data_quality_flag recomputation
# ---------------------------------------------------------------------------


def _compute_data_quality_flag(
    source_type: str,
    ocr_confidence: float | None,
    route_resolved: bool,
) -> str:
    """Compute data_quality_flag per V8 Section 6.3 priority rules.

    Called at enrichment row creation AND when enrichment completes.
    ocr_confidence is read from trip_trip_evidence.
    """
    if source_type in (SourceType.ADMIN_MANUAL, SourceType.EMPTY_RETURN_ADMIN, SourceType.EXCEL_IMPORT):
        return DataQualityFlag.HIGH
    # TELEGRAM_TRIP_SLIP truth table (V8 Section 6.3):
    # ocr>=0.90 AND route_resolved → HIGH
    # ocr>=0.70                    → MEDIUM (regardless of route)
    # not route_resolved           → MEDIUM (regardless of confidence)
    # ocr<0.70 AND route_resolved  → LOW
    # ocr=None AND route_resolved  → LOW (no confidence signal)
    if ocr_confidence is not None and ocr_confidence >= 0.90 and route_resolved:
        return DataQualityFlag.HIGH
    if ocr_confidence is not None and ocr_confidence >= 0.70:
        return DataQualityFlag.MEDIUM
    if not route_resolved:
        return DataQualityFlag.MEDIUM
    return DataQualityFlag.LOW


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


# ---------------------------------------------------------------------------
# External Service Clients (injectable, abstract)
# ---------------------------------------------------------------------------


async def _resolve_route(origin_name: str, destination_name: str) -> tuple[str | None, str]:
    """Call Location Service to resolve route.

    V8 Section 7.2: POST /internal/v1/routes/resolve
    Returns (route_id, status) where status is READY/FAILED.
    """
    try:
        client = await get_worker_client()
        resp = await client.post(
            f"{settings.location_service_url}/internal/v1/routes/resolve",
            json={
                "origin_name": origin_name,
                "destination_name": destination_name,
                "profile_code": "TIR",
                "language_hint": "AUTO",
            },
            headers=_location_service_headers(),
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("route_id"), RouteStatus.READY
        problem_code = _problem_code(resp)
        if resp.status_code in {404, 422} and problem_code in {
            "LOCATION_ROUTE_RESOLUTION_NOT_FOUND",
            "ROUTE_AMBIGUOUS",
        }:
            logger.info(
                "Route resolution skipped as business-invalid: status=%d code=%s",
                resp.status_code,
                problem_code,
            )
            return None, RouteStatus.SKIPPED
        logger.warning("Route resolution failed: status=%d code=%s", resp.status_code, problem_code)
        return None, RouteStatus.FAILED
    except Exception as e:
        logger.error("Route resolution error: %s", e)
        return None, RouteStatus.FAILED


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
        ENRICHMENT_CLAIMED_TOTAL.inc(len(enrichment_rows))

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


async def _process_single_enrichment(
    trip_id: str,
    enrichment_id: str,
    claim_token: str,
    worker_id: str,
) -> None:
    """Process a single enrichment row.

    Handles route resolution → final status derivation.
    """
    async with async_session_factory() as session:
        # Reload enrichment row with trip
        stmt = select(TripTripEnrichment).where(
            TripTripEnrichment.id == enrichment_id,
            TripTripEnrichment.claim_token == claim_token,
        )
        result = await session.execute(stmt)
        enrichment = result.scalar_one_or_none()

        if enrichment is None:
            logger.warning("Enrichment %s: claim lost (token mismatch), skipping", enrichment_id)
            return

        # Load trip for context
        trip_result = await session.execute(select(TripTrip).where(TripTrip.id == trip_id))
        trip = trip_result.scalar_one_or_none()
        if trip is None:
            logger.warning("Enrichment %s: trip %s not found, skipping", enrichment_id, trip_id)
            return

        # Load evidence for ocr_confidence (for data_quality_flag recomputation)
        ev_result = await session.execute(
            select(TripTripEvidence)
            .where(TripTripEvidence.trip_id == trip_id)
            .order_by(TripTripEvidence.created_at_utc.desc())
            .limit(1)
        )
        evidence = ev_result.scalar_one_or_none()
        ocr_confidence = evidence.ocr_confidence if evidence else None

        now = _now_utc()
        route_resolved = False

        try:
            # --- Route resolution ---
            if enrichment.route_status == RouteStatus.PENDING:
                if evidence and evidence.origin_name_raw and evidence.destination_name_raw:
                    route_id, route_status = await _resolve_route(
                        evidence.origin_name_raw,
                        evidence.destination_name_raw,
                    )
                    enrichment.route_status = route_status
                    if route_id:
                        trip.route_id = route_id
                        route_resolved = True
                else:
                    # No evidence for route resolution
                    enrichment.route_status = RouteStatus.FAILED
            elif enrichment.route_status == RouteStatus.READY:
                route_resolved = True

            # --- Derive final enrichment status (V8 Section 13.8) ---
            enrichment.enrichment_status = _derive_final_enrichment_status(enrichment.route_status)

            # --- Recompute data_quality_flag (V8 Section 6.3) ---
            enrichment.data_quality_flag = _compute_data_quality_flag(
                trip.source_type,
                ocr_confidence,
                route_resolved=route_resolved,
            )

            # --- Step 5: Clear claim fields on finish ---
            enrichment.claim_token = None
            enrichment.claim_expires_at_utc = None
            enrichment.claimed_by_worker = None
            enrichment.last_enrichment_error_code = None
            enrichment.updated_at_utc = now

            # If still need retries (PENDING or FAILED with attempts left)
            # BUG-07 fix: compute retry time BEFORE incrementing attempt_count so
            # attempt 0 → index 0 → 60s (V8 Section 13.7: first retry = 1 minute).
            if enrichment.enrichment_status in (EnrichmentStatus.PENDING, EnrichmentStatus.FAILED):
                if enrichment.enrichment_attempt_count < settings.enrichment_max_attempts:
                    enrichment.next_retry_at_utc = _enrichment_next_retry_at(enrichment.enrichment_attempt_count)
                else:
                    # Max attempts reached → FAILED
                    enrichment.enrichment_status = EnrichmentStatus.FAILED
                    enrichment.next_retry_at_utc = None
                    ENRICHMENT_FAILED_TOTAL.inc()
            else:
                enrichment.next_retry_at_utc = None
            enrichment.enrichment_attempt_count += 1

            await session.commit()
            ENRICHMENT_COMPLETED_TOTAL.labels(result=enrichment.enrichment_status).inc()

            logger.info(
                "Enrichment %s: completed — route=%s enrichment=%s quality=%s",
                enrichment_id,
                enrichment.route_status,
                enrichment.enrichment_status,
                enrichment.data_quality_flag,
            )

        except Exception as e:
            logger.error("Enrichment %s: processing error: %s", enrichment_id, e)
            # On error: clear claim, mark FAILED, schedule retry
            enrichment.enrichment_status = EnrichmentStatus.FAILED
            enrichment.claim_token = None
            enrichment.claim_expires_at_utc = None
            enrichment.claimed_by_worker = None
            enrichment.last_enrichment_error_code = str(e)[:100]
            enrichment.updated_at_utc = now

            # BUG-07 fix: compute retry using current count (before increment)
            if enrichment.enrichment_attempt_count < settings.enrichment_max_attempts:
                enrichment.next_retry_at_utc = _enrichment_next_retry_at(enrichment.enrichment_attempt_count)
            else:
                enrichment.next_retry_at_utc = None
                ENRICHMENT_FAILED_TOTAL.inc()
            enrichment.enrichment_attempt_count += 1

            await session.commit()


# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------


async def run_enrichment_worker(worker_id: str | None = None) -> None:
    """Main enrichment worker loop.

    Runs indefinitely, polling for work at configured intervals.
    Multiple instances are safe (claim locking).
    """
    if worker_id is None:
        worker_id = f"worker-{uuid.uuid4().hex[:8]}"

    logger.info("Enrichment worker %s starting", worker_id)

    while True:
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

        await asyncio.sleep(settings.enrichment_poll_interval_seconds)
