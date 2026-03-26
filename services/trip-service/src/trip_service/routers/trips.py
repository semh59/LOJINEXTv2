"""Trip endpoints router — V8 Section 10 API contracts.

This is the main router for all trip-related API endpoints.
Implements all 18 endpoints from the V8 specification.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from ulid import ULID

from trip_service.database import get_session
from trip_service.enums import (
    ActorType,
    DataQualityFlag,
    EnrichmentStatus,
    EvidenceKind,
    EvidenceSource,
    RouteStatus,
    SourceType,
    TripStatus,
)
from trip_service.errors import (
    empty_return_already_exists,
    enrichment_already_running,
    has_empty_return_child,
    idempotency_payload_mismatch,
    invalid_base_for_empty_return,
    invalid_filter_combination,
    invalid_status_transition,
    route_required_for_completion,
    trip_no_conflict,
    trip_not_found,
    trip_version_mismatch,
)
from trip_service.middleware import (
    date_range_to_utc,
    make_etag,
    make_pagination_meta,
    parse_pagination,
    require_if_match,
)
from trip_service.models import (
    TripIdempotencyRecord,
    TripOutbox,
    TripTrip,
    TripTripEnrichment,
    TripTripEvidence,
    TripTripTimeline,
)
from trip_service.schemas import (
    ApproveRequest,
    EditTripRequest,
    EmptyReturnRequest,
    EnrichmentSummary,
    EvidenceSummary,
    IngestSlipRequest,
    ManualCreateRequest,
    RetryEnrichmentResponse,
    TimelineItem,
    TripResource,
)

router = APIRouter(tags=["trips"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_id() -> str:
    """Generate a ULID string for primary keys."""
    return str(ULID())


def _now_utc() -> datetime:
    """Current UTC timestamp."""
    return datetime.now(tz=ZoneInfo("UTC"))


def _local_to_utc(local_str: str, timezone: str) -> datetime:
    """Convert a local datetime string + timezone to UTC datetime."""
    tz = ZoneInfo(timezone)
    local_dt = datetime.fromisoformat(local_str).replace(tzinfo=tz)
    return local_dt.astimezone(ZoneInfo("UTC"))


def _canonicalize_body(body: dict[str, Any]) -> str:
    """SHA-256 of a canonicalized request body (sorted keys, no whitespace)."""
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _trip_to_resource(trip: TripTrip) -> TripResource:
    """Map ORM model to API resource."""
    enrichment_summary = None
    if trip.enrichment:
        enrichment_summary = EnrichmentSummary(
            enrichment_status=trip.enrichment.enrichment_status,
            route_status=trip.enrichment.route_status,
            data_quality_flag=trip.enrichment.data_quality_flag,
        )

    # BUG-05: Use max(created_at_utc) instead of [-1] which is load-order
    # dependent (undefined for eagerly-loaded collections).
    evidence_summary = None
    if trip.evidence:
        ev = max(trip.evidence, key=lambda e: e.created_at_utc)
        evidence_summary = EvidenceSummary(
            normalized_truck_plate=ev.normalized_truck_plate,
            normalized_trailer_plate=ev.normalized_trailer_plate,
            origin_name_raw=ev.origin_name_raw,
            destination_name_raw=ev.destination_name_raw,
        )

    return TripResource(
        id=trip.id,
        trip_no=trip.trip_no,
        source_type=trip.source_type,
        source_slip_no=trip.source_slip_no,
        base_trip_id=trip.base_trip_id,
        driver_id=trip.driver_id,
        vehicle_id=trip.vehicle_id,
        trailer_id=trip.trailer_id,
        route_id=trip.route_id,
        trip_datetime_utc=trip.trip_datetime_utc,
        trip_timezone=trip.trip_timezone,
        tare_weight_kg=trip.tare_weight_kg,
        gross_weight_kg=trip.gross_weight_kg,
        net_weight_kg=trip.net_weight_kg,
        is_empty_return=trip.is_empty_return,
        status=trip.status,
        version=trip.version,
        enrichment=enrichment_summary,
        evidence_summary=evidence_summary,
        created_at_utc=trip.created_at_utc,
        updated_at_utc=trip.updated_at_utc,
        soft_deleted_at_utc=trip.soft_deleted_at_utc,
    )


async def _get_trip_or_404(session: AsyncSession, trip_id: str) -> TripTrip:
    """Load trip with enrichment + evidence eagerly, or raise 404."""
    stmt = (
        select(TripTrip)
        .options(selectinload(TripTrip.enrichment), selectinload(TripTrip.evidence))
        .where(TripTrip.id == trip_id)
    )
    result = await session.execute(stmt)
    trip = result.scalar_one_or_none()
    if trip is None:
        raise trip_not_found(trip_id)
    return trip


def _compute_data_quality_flag(source_type: str, ocr_confidence: float | None, route_resolved: bool) -> str:
    """V8 Section 6.3 — data_quality_flag computation."""
    if source_type in (SourceType.ADMIN_MANUAL, SourceType.EMPTY_RETURN_ADMIN, SourceType.EXCEL_IMPORT):
        return DataQualityFlag.HIGH
    # TELEGRAM_TRIP_SLIP
    if ocr_confidence is not None and ocr_confidence >= 0.90 and route_resolved:
        return DataQualityFlag.HIGH
    if ocr_confidence is not None and ocr_confidence >= 0.70:
        return DataQualityFlag.MEDIUM
    if not route_resolved:
        return DataQualityFlag.MEDIUM
    return DataQualityFlag.LOW


def _create_outbox_event(
    trip: TripTrip,
    event_name: str,
    payload: dict[str, Any],
) -> TripOutbox:
    """Create a transactional outbox row."""
    return TripOutbox(
        event_id=_generate_id(),
        aggregate_type="TRIP",
        aggregate_id=trip.id,
        aggregate_version=trip.version,
        event_name=event_name,
        schema_version=1,
        payload_json=json.dumps(payload, default=str),
        partition_key=trip.id,
        publish_status="PENDING",
        attempt_count=0,
        created_at_utc=_now_utc(),
    )


async def _check_idempotency_key(
    session: AsyncSession,
    idempotency_key: str | None,
    endpoint_fingerprint: str,
    request_hash: str,
) -> JSONResponse | None:
    """V8 Section 15.2 — Admin POST idempotency check.

    Returns a replay response if idempotency key was already used,
    raises 409 if same key + different payload, or None for new request.
    """
    if not idempotency_key:
        return None

    stmt = select(TripIdempotencyRecord).where(
        TripIdempotencyRecord.idempotency_key == idempotency_key,
        TripIdempotencyRecord.endpoint_fingerprint == endpoint_fingerprint,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is None:
        return None

    if existing.request_hash != request_hash:
        raise idempotency_payload_mismatch()

    # Replay original response
    return JSONResponse(
        status_code=existing.response_status,
        content=json.loads(existing.response_body_json),
    )


async def _save_idempotency_record(
    session: AsyncSession,
    idempotency_key: str,
    endpoint_fingerprint: str,
    request_hash: str,
    response_status: int,
    response_body: dict[str, Any],
) -> None:
    """Persist idempotency record for replay."""
    now = _now_utc()
    record = TripIdempotencyRecord(
        idempotency_key=idempotency_key,
        endpoint_fingerprint=endpoint_fingerprint,
        request_hash=request_hash,
        response_status=response_status,
        response_body_json=json.dumps(response_body, default=str),
        created_at_utc=now,
        expires_at_utc=now + timedelta(hours=24),
    )
    session.add(record)


# ---------------------------------------------------------------------------
# V8 Section 10.1 — Ingest Trip Slip
# ---------------------------------------------------------------------------


@router.post("/internal/v1/trips/slips/ingest", status_code=201)
async def ingest_trip_slip(
    body: IngestSlipRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Any:
    """V8 Section 10.1 — Ingest normalized trip slip from Slip Processing Service."""
    request_hash = _canonicalize_body(body.model_dump())

    # Idempotency check by source_slip_no (authoritative)
    stmt = select(TripTrip).where(
        TripTrip.source_slip_no == body.source_slip_no,
        TripTrip.source_type == SourceType.TELEGRAM_TRIP_SLIP,
    )
    result = await session.execute(stmt)
    existing_trip = result.scalar_one_or_none()

    if existing_trip is not None:
        if existing_trip.source_payload_hash == request_hash:
            # Idempotent replay
            stmt2 = (
                select(TripTrip)
                .options(selectinload(TripTrip.enrichment), selectinload(TripTrip.evidence))
                .where(TripTrip.id == existing_trip.id)
            )
            result2 = await session.execute(stmt2)
            trip = result2.scalar_one()
            resource = _trip_to_resource(trip)
            resp = JSONResponse(
                status_code=200,
                content=resource.model_dump(mode="json"),
            )
            resp.headers["ETag"] = make_etag(trip.id, trip.version)
            return resp
        else:
            raise idempotency_payload_mismatch()

    # New trip creation
    now = _now_utc()
    trip_id = _generate_id()
    trip_datetime_utc = _local_to_utc(body.trip_datetime_local, body.trip_timezone)

    trip = TripTrip(
        id=trip_id,
        trip_no=body.source_slip_no,  # V8: trip_no = source_slip_no
        source_type=SourceType.TELEGRAM_TRIP_SLIP,
        source_slip_no=body.source_slip_no,
        source_payload_hash=request_hash,
        driver_id=body.driver_id,
        vehicle_id=body.vehicle_id,
        trailer_id=body.trailer_id,
        route_id=None,  # Route resolved by enrichment
        trip_datetime_utc=trip_datetime_utc,
        trip_timezone=body.trip_timezone,
        tare_weight_kg=body.tare_weight_kg,
        gross_weight_kg=body.gross_weight_kg,
        net_weight_kg=body.net_weight_kg,
        is_empty_return=False,
        status=TripStatus.PENDING_REVIEW,
        version=1,
        created_by_actor_type=ActorType.SYSTEM,
        created_by_actor_id="slip-processing-service",
        created_at_utc=now,
        updated_at_utc=now,
    )
    session.add(trip)

    # Evidence row
    evidence = TripTripEvidence(
        id=_generate_id(),
        trip_id=trip_id,
        evidence_source=EvidenceSource.TELEGRAM_TRIP_SLIP,
        evidence_kind=EvidenceKind.SLIP_IMAGE,
        source_slip_no=body.source_slip_no,
        file_key=body.file_key,
        raw_text_ref=body.raw_text_ref,
        ocr_confidence=body.ocr_confidence,
        normalized_truck_plate=body.normalized_truck_plate,
        normalized_trailer_plate=body.normalized_trailer_plate,
        origin_name_raw=body.origin_name,
        destination_name_raw=body.destination_name,
        raw_payload_json=json.dumps(body.model_dump(), default=str),
        created_at_utc=now,
    )
    session.add(evidence)

    # Enrichment row
    data_quality = _compute_data_quality_flag(
        SourceType.TELEGRAM_TRIP_SLIP,
        body.ocr_confidence,
        route_resolved=False,
    )
    enrichment = TripTripEnrichment(
        id=_generate_id(),
        trip_id=trip_id,
        enrichment_status=EnrichmentStatus.PENDING,
        route_status=RouteStatus.PENDING,
        data_quality_flag=data_quality,
        enrichment_attempt_count=0,
        created_at_utc=now,
        updated_at_utc=now,
    )
    session.add(enrichment)

    # Timeline
    timeline = TripTripTimeline(
        id=_generate_id(),
        trip_id=trip_id,
        event_type="TRIP_CREATED",
        actor_type=ActorType.SYSTEM,
        actor_id="slip-processing-service",
        note=f"Trip ingested from slip {body.source_slip_no}",
        created_at_utc=now,
    )
    session.add(timeline)

    # Outbox: trip.created.v1
    outbox = _create_outbox_event(
        trip,
        "trip.created.v1",
        {
            "trip_id": trip_id,
            "trip_no": trip.trip_no,
            "source_type": trip.source_type,
            "driver_id": trip.driver_id,
            "vehicle_id": trip.vehicle_id,
            "trailer_id": trip.trailer_id,
            "route_id": trip.route_id,
            "trip_datetime_utc": str(trip.trip_datetime_utc),
            "status": trip.status,
            "enrichment_status": enrichment.enrichment_status,
        },
    )
    session.add(outbox)

    await session.commit()

    # Reload with relationships
    trip = await _get_trip_or_404(session, trip_id)
    resource = _trip_to_resource(trip)

    resp = JSONResponse(status_code=201, content=resource.model_dump(mode="json"))
    resp.headers["ETag"] = make_etag(trip.id, trip.version)
    return resp


# ---------------------------------------------------------------------------
# V8 Section 10.2 — Create Manual Trip
# ---------------------------------------------------------------------------


@router.post("/api/v1/trips", status_code=201)
async def create_manual_trip(
    body: ManualCreateRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    x_actor_type: str = Header(..., alias="X-Actor-Type"),
    x_actor_id: str = Header(..., alias="X-Actor-Id"),
) -> Any:
    """V8 Section 10.2 — Admin manual trip creation (directly COMPLETED)."""
    request_body = body.model_dump(exclude_none=True)
    request_hash = _canonicalize_body(request_body)
    endpoint_fp = f"create_trip:{x_actor_id}"

    # Idempotency check
    replay = await _check_idempotency_key(session, idempotency_key, endpoint_fp, request_hash)
    if replay is not None:
        return replay

    # Check trip_no uniqueness
    existing = await session.execute(select(TripTrip).where(TripTrip.trip_no == body.trip_no))
    if existing.scalar_one_or_none() is not None:
        raise trip_no_conflict(body.trip_no)

    now = _now_utc()
    trip_id = _generate_id()
    trip_datetime_utc = _local_to_utc(body.trip_datetime_local, body.trip_timezone)

    trip = TripTrip(
        id=trip_id,
        trip_no=body.trip_no,
        source_type=SourceType.ADMIN_MANUAL,
        driver_id=body.driver_id,
        vehicle_id=body.vehicle_id,
        trailer_id=body.trailer_id,
        route_id=body.route_id,
        trip_datetime_utc=trip_datetime_utc,
        trip_timezone=body.trip_timezone,
        tare_weight_kg=body.tare_weight_kg,
        gross_weight_kg=body.gross_weight_kg,
        net_weight_kg=body.net_weight_kg,
        is_empty_return=False,  # Server-enforced
        status=TripStatus.COMPLETED,
        version=1,
        created_by_actor_type=x_actor_type,
        created_by_actor_id=x_actor_id,
        created_at_utc=now,
        updated_at_utc=now,
    )
    session.add(trip)

    # Enrichment row: route READY (provided)
    enrichment = TripTripEnrichment(
        id=_generate_id(),
        trip_id=trip_id,
        enrichment_status=EnrichmentStatus.PENDING,
        route_status=RouteStatus.READY,
        data_quality_flag=DataQualityFlag.HIGH,
        enrichment_attempt_count=0,
        created_at_utc=now,
        updated_at_utc=now,
    )
    session.add(enrichment)

    # Optional manual evidence
    if body.note:
        evidence = TripTripEvidence(
            id=_generate_id(),
            trip_id=trip_id,
            evidence_source=EvidenceSource.ADMIN_MANUAL,
            evidence_kind=EvidenceKind.MANUAL_ENTRY,
            raw_payload_json=json.dumps(request_body, default=str),
            created_at_utc=now,
        )
        session.add(evidence)

    # Timeline
    timeline = TripTripTimeline(
        id=_generate_id(),
        trip_id=trip_id,
        event_type="TRIP_CREATED",
        actor_type=x_actor_type,
        actor_id=x_actor_id,
        note=body.note or "Manual trip created by admin",
        created_at_utc=now,
    )
    session.add(timeline)

    # Outbox: trip.created.v1 + trip.completed.v1
    for event_name in ("trip.created.v1", "trip.completed.v1"):
        outbox = _create_outbox_event(
            trip,
            event_name,
            {
                "trip_id": trip_id,
                "trip_no": trip.trip_no,
                "source_type": trip.source_type,
                "driver_id": trip.driver_id,
                "vehicle_id": trip.vehicle_id,
                "trailer_id": trip.trailer_id,
                "route_id": trip.route_id,
                "trip_datetime_utc": str(trip.trip_datetime_utc),
                "status": trip.status,
                "enrichment_status": enrichment.enrichment_status,
                "tare_weight_kg": trip.tare_weight_kg,
                "gross_weight_kg": trip.gross_weight_kg,
                "net_weight_kg": trip.net_weight_kg,
                "is_empty_return": trip.is_empty_return,
                "route_status": enrichment.route_status,
            },
        )
        session.add(outbox)

    await session.commit()

    trip = await _get_trip_or_404(session, trip_id)
    resource = _trip_to_resource(trip)
    resource_dict = resource.model_dump(mode="json")

    # Save idempotency record
    if idempotency_key:
        await _save_idempotency_record(session, idempotency_key, endpoint_fp, request_hash, 201, resource_dict)
        await session.commit()

    resp = JSONResponse(status_code=201, content=resource_dict)
    resp.headers["ETag"] = make_etag(trip.id, trip.version)
    return resp


# ---------------------------------------------------------------------------
# V8 Section 10.3 — List Trips (Admin)
# ---------------------------------------------------------------------------


@router.get("/api/v1/trips")
async def list_trips(
    request: Request,
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    status: str | None = Query(None),
    source_type: str | None = Query(None),
    driver_id: str | None = Query(None),
    vehicle_id: str | None = Query(None),
    route_id: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    timezone: str = Query("Europe/Istanbul"),
    trip_no: str | None = Query(None),
    include_soft_deleted: bool = Query(False),
) -> dict[str, Any]:
    """V8 Section 10.3 — Admin list trips with filters."""
    # V8: status=SOFT_DELETED only valid with include_soft_deleted=true
    if status == TripStatus.SOFT_DELETED and not include_soft_deleted:
        raise invalid_filter_combination("status=SOFT_DELETED requires include_soft_deleted=true")

    pagination = parse_pagination(page, per_page)

    # Build query
    base_q = select(TripTrip).options(selectinload(TripTrip.enrichment), selectinload(TripTrip.evidence))

    # Default: exclude soft-deleted
    if not include_soft_deleted:
        base_q = base_q.where(TripTrip.status != TripStatus.SOFT_DELETED)

    if status:
        base_q = base_q.where(TripTrip.status == status)
    if source_type:
        base_q = base_q.where(TripTrip.source_type == source_type)
    if driver_id:
        base_q = base_q.where(TripTrip.driver_id == driver_id)
    if vehicle_id:
        base_q = base_q.where(TripTrip.vehicle_id == vehicle_id)
    if route_id:
        base_q = base_q.where(TripTrip.route_id == route_id)
    if trip_no:
        base_q = base_q.where(TripTrip.trip_no == trip_no)

    # Timezone date filter V8 Section 8.4
    if date_from or date_to:
        utc_from, utc_to = date_range_to_utc(date_from, date_to, timezone)
        if utc_from:
            base_q = base_q.where(TripTrip.trip_datetime_utc >= utc_from)
        if utc_to:
            base_q = base_q.where(TripTrip.trip_datetime_utc < utc_to)

    # Count total
    count_q = select(func.count()).select_from(base_q.subquery())
    total_items = (await session.execute(count_q)).scalar() or 0

    # Sort: trip_datetime_utc DESC, id DESC (V8 Section 8.3)
    items_q = (
        base_q.order_by(TripTrip.trip_datetime_utc.desc(), TripTrip.id.desc())
        .offset(pagination.offset)
        .limit(pagination.per_page)
    )
    results = await session.execute(items_q)
    trips = results.scalars().all()

    return {
        "items": [_trip_to_resource(t).model_dump(mode="json") for t in trips],
        "meta": make_pagination_meta(pagination.page, pagination.per_page, total_items),
    }


# ---------------------------------------------------------------------------
# V8 Section 10.4 — Get Trip Detail
# ---------------------------------------------------------------------------


@router.get("/api/v1/trips/{trip_id}")
async def get_trip_detail(
    trip_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Any:
    """V8 Section 10.4 — Returns trip including soft-deleted."""
    trip = await _get_trip_or_404(session, trip_id)
    resource = _trip_to_resource(trip)
    resp = JSONResponse(status_code=200, content=resource.model_dump(mode="json"))
    resp.headers["ETag"] = make_etag(trip.id, trip.version)
    return resp


# ---------------------------------------------------------------------------
# V8 Section 10.5 — Get Trip Timeline
# ---------------------------------------------------------------------------


@router.get("/api/v1/trips/{trip_id}/timeline")
async def get_trip_timeline(
    trip_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """V8 Section 10.5 — All timeline items, sorted created_at_utc ASC (chronological)."""
    # Verify trip exists
    await _get_trip_or_404(session, trip_id)

    stmt = (
        select(TripTripTimeline)
        .where(TripTripTimeline.trip_id == trip_id)
        .order_by(TripTripTimeline.created_at_utc.asc())  # V8: chronological ASC
    )
    results = await session.execute(stmt)
    items = results.scalars().all()

    return {
        "items": [TimelineItem.model_validate(i).model_dump(mode="json") for i in items],
    }


# ---------------------------------------------------------------------------
# V8 Section 10.6 — Edit Trip
# ---------------------------------------------------------------------------


@router.patch("/api/v1/trips/{trip_id}")
async def edit_trip(
    trip_id: str,
    body: EditTripRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    x_actor_type: str = Header(..., alias="X-Actor-Type"),
    x_actor_id: str = Header(..., alias="X-Actor-Id"),
) -> Any:
    """V8 Section 10.6 — Edit trip with optimistic locking."""
    # BUG-01: Check header ONCE, store result; avoids redundant parse and
    # ensures 428 fires before any DB read when header is absent.
    parsed = require_if_match(request)
    trip = await _get_trip_or_404(session, trip_id)

    if parsed[1] != trip.version:
        raise trip_version_mismatch()

    # V8: Allowed only on COMPLETED and PENDING_REVIEW
    if trip.status not in (TripStatus.COMPLETED, TripStatus.PENDING_REVIEW):
        raise invalid_status_transition("Cannot edit a trip with this status.")

    now = _now_utc()
    changed_fields: list[str] = []
    route_sensitive_changed = False

    update_data = body.model_dump(exclude_unset=True)

    # BUG-02: Handle trip_datetime_local + trip_timezone as a unit BEFORE the
    # generic field loop so they are not double-processed.
    if "trip_datetime_local" in update_data or "trip_timezone" in update_data:
        tz = update_data.get("trip_timezone", trip.trip_timezone)
        if "trip_datetime_local" in update_data:
            new_utc = _local_to_utc(update_data["trip_datetime_local"], tz)
            if new_utc != trip.trip_datetime_utc:
                trip.trip_datetime_utc = new_utc
                changed_fields.append("trip_datetime_utc")
                route_sensitive_changed = True
        if "trip_timezone" in update_data and update_data["trip_timezone"] != trip.trip_timezone:
            trip.trip_timezone = update_data["trip_timezone"]
            changed_fields.append("trip_timezone")
            route_sensitive_changed = True

    # BUG-03: Fields that should reset enrichment on change.
    _enrichment_sensitive = {
        "driver_id",
        "vehicle_id",
        "trailer_id",
        "tare_weight_kg",
        "gross_weight_kg",
        "net_weight_kg",
    }

    for field_name, value in update_data.items():
        if field_name in ("trip_datetime_local", "trip_timezone"):
            continue  # already handled above
        elif field_name == "route_id":
            if value != trip.route_id:
                trip.route_id = value
                changed_fields.append("route_id")
                route_sensitive_changed = True
        elif hasattr(trip, field_name):
            old_val = getattr(trip, field_name)
            if old_val != value:
                setattr(trip, field_name, value)
                changed_fields.append(field_name)
                if field_name in _enrichment_sensitive:
                    route_sensitive_changed = True

    if not changed_fields:
        resource = _trip_to_resource(trip)
        resp = JSONResponse(status_code=200, content=resource.model_dump(mode="json"))
        resp.headers["ETag"] = make_etag(trip.id, trip.version)
        return resp

    # V8 Section 10.6: Route-sensitive field changes → reset enrichment
    if route_sensitive_changed and trip.enrichment:
        enrichment = trip.enrichment
        enrichment.route_status = RouteStatus.PENDING  # BUG-03 fix: always reset
        enrichment.enrichment_status = EnrichmentStatus.PENDING
        enrichment.claim_token = None
        enrichment.claim_expires_at_utc = None
        enrichment.claimed_by_worker = None
        enrichment.next_retry_at_utc = None
        enrichment.updated_at_utc = now
        session.add(enrichment)

    trip.version += 1
    trip.updated_at_utc = now

    # Timeline
    timeline = TripTripTimeline(
        id=_generate_id(),
        trip_id=trip_id,
        event_type="TRIP_EDITED",
        actor_type=x_actor_type,
        actor_id=x_actor_id,
        note=f"Fields changed: {', '.join(changed_fields)}",
        payload_json=json.dumps({"changed_fields": changed_fields}),
        created_at_utc=now,
    )
    session.add(timeline)

    # Outbox: trip.edited.v1
    outbox = _create_outbox_event(
        trip,
        "trip.edited.v1",
        {
            "trip_id": trip.id,
            "trip_no": trip.trip_no,
            "status": trip.status,
            "edited_by_actor_id": x_actor_id,
            "edited_at_utc": str(now),
            "changed_fields": changed_fields,
            "driver_id": trip.driver_id,
            "vehicle_id": trip.vehicle_id,
            "trailer_id": trip.trailer_id,
            "route_id": trip.route_id,
            "trip_datetime_utc": str(trip.trip_datetime_utc),
            "tare_weight_kg": trip.tare_weight_kg,
            "gross_weight_kg": trip.gross_weight_kg,
            "net_weight_kg": trip.net_weight_kg,
        },
    )
    session.add(outbox)

    await session.commit()
    trip = await _get_trip_or_404(session, trip_id)
    resource = _trip_to_resource(trip)
    resp = JSONResponse(status_code=200, content=resource.model_dump(mode="json"))
    resp.headers["ETag"] = make_etag(trip.id, trip.version)
    return resp


# ---------------------------------------------------------------------------
# V8 Section 10.7 — Approve Pending Trip
# ---------------------------------------------------------------------------


@router.post("/api/v1/trips/{trip_id}/approve")
async def approve_trip(
    trip_id: str,
    body: ApproveRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    x_actor_type: str = Header(..., alias="X-Actor-Type"),
    x_actor_id: str = Header(..., alias="X-Actor-Id"),
) -> Any:
    """V8 Section 10.7 — Approve PENDING_REVIEW → COMPLETED."""
    # BUG-11: Check If-Match header before DB load so 428 fires without a
    # wasted query when the header is missing.
    parsed = require_if_match(request)
    trip = await _get_trip_or_404(session, trip_id)
    if parsed[1] != trip.version:
        raise trip_version_mismatch()

    if trip.status != TripStatus.PENDING_REVIEW:
        raise invalid_status_transition("Only PENDING_REVIEW trips can be approved.")

    if not trip.enrichment or trip.enrichment.route_status != RouteStatus.READY:
        raise route_required_for_completion()

    now = _now_utc()
    trip.status = TripStatus.COMPLETED
    trip.version += 1
    trip.updated_at_utc = now

    # Timeline
    timeline = TripTripTimeline(
        id=_generate_id(),
        trip_id=trip_id,
        event_type="TRIP_APPROVED",
        actor_type=x_actor_type,
        actor_id=x_actor_id,
        note=body.note or "Trip approved",
        created_at_utc=now,
    )
    session.add(timeline)

    # Outbox: trip.completed.v1
    outbox = _create_outbox_event(
        trip,
        "trip.completed.v1",
        {
            "trip_id": trip.id,
            "trip_no": trip.trip_no,
            "source_type": trip.source_type,
            "status": trip.status,
            "driver_id": trip.driver_id,
            "vehicle_id": trip.vehicle_id,
            "trailer_id": trip.trailer_id,
            "route_id": trip.route_id,
            "trip_datetime_utc": str(trip.trip_datetime_utc),
            "tare_weight_kg": trip.tare_weight_kg,
            "gross_weight_kg": trip.gross_weight_kg,
            "net_weight_kg": trip.net_weight_kg,
            "is_empty_return": trip.is_empty_return,
            "route_status": trip.enrichment.route_status,
            "enrichment_status": trip.enrichment.enrichment_status,
        },
    )
    session.add(outbox)

    await session.commit()
    trip = await _get_trip_or_404(session, trip_id)
    resource = _trip_to_resource(trip)
    resp = JSONResponse(status_code=200, content=resource.model_dump(mode="json"))
    resp.headers["ETag"] = make_etag(trip.id, trip.version)
    return resp


# ---------------------------------------------------------------------------
# V8 Section 10.8 — Create Empty Return Trip
# ---------------------------------------------------------------------------


@router.post("/api/v1/trips/{base_trip_id}/empty-return", status_code=201)
async def create_empty_return(
    base_trip_id: str,
    body: EmptyReturnRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    x_actor_type: str = Header(..., alias="X-Actor-Type"),
    x_actor_id: str = Header(..., alias="X-Actor-Id"),
) -> Any:
    """V8 Section 10.8 — Create derivative empty-return trip."""
    base_trip = await _get_trip_or_404(session, base_trip_id)
    parsed = require_if_match(request)
    if parsed[1] != base_trip.version:
        raise trip_version_mismatch()

    # Validate base trip
    if base_trip.status == TripStatus.SOFT_DELETED:
        raise invalid_base_for_empty_return("Base trip is soft deleted.")
    if base_trip.is_empty_return:
        raise invalid_base_for_empty_return("Base trip is itself an empty-return trip.")

    # Check existing empty return
    existing = await session.execute(
        select(TripTrip).where(TripTrip.base_trip_id == base_trip_id, TripTrip.is_empty_return.is_(True))
    )
    if existing.scalar_one_or_none() is not None:
        raise empty_return_already_exists()

    # Idempotency check
    # BUG-12: Include base_trip_id in fingerprint so the same actor can create
    # empty-returns for different base trips without collision.
    request_body = body.model_dump(exclude_none=True)
    request_hash = _canonicalize_body(request_body)
    endpoint_fp = f"empty_return:{x_actor_id}:{base_trip_id}"
    replay = await _check_idempotency_key(session, idempotency_key, endpoint_fp, request_hash)
    if replay is not None:
        return replay

    now = _now_utc()
    trip_id = _generate_id()
    trip_datetime_utc = _local_to_utc(body.trip_datetime_local, body.trip_timezone)

    # V8: trip_no = {base_trip_no}B
    empty_return_trip_no = f"{base_trip.trip_no}B"

    trip = TripTrip(
        id=trip_id,
        trip_no=empty_return_trip_no,
        source_type=SourceType.EMPTY_RETURN_ADMIN,
        base_trip_id=base_trip_id,
        driver_id=body.driver_id,
        vehicle_id=body.vehicle_id,
        trailer_id=body.trailer_id,
        route_id=body.route_id,
        trip_datetime_utc=trip_datetime_utc,
        trip_timezone=body.trip_timezone,
        tare_weight_kg=body.tare_weight_kg,
        gross_weight_kg=body.gross_weight_kg,
        net_weight_kg=body.net_weight_kg,
        is_empty_return=True,
        status=TripStatus.COMPLETED,
        version=1,
        created_by_actor_type=x_actor_type,
        created_by_actor_id=x_actor_id,
        created_at_utc=now,
        updated_at_utc=now,
    )
    session.add(trip)

    # Enrichment: route READY
    enrichment = TripTripEnrichment(
        id=_generate_id(),
        trip_id=trip_id,
        enrichment_status=EnrichmentStatus.PENDING,
        route_status=RouteStatus.READY,
        data_quality_flag=DataQualityFlag.HIGH,
        enrichment_attempt_count=0,
        created_at_utc=now,
        updated_at_utc=now,
    )
    session.add(enrichment)

    # Timeline
    timeline = TripTripTimeline(
        id=_generate_id(),
        trip_id=trip_id,
        event_type="TRIP_CREATED",
        actor_type=x_actor_type,
        actor_id=x_actor_id,
        note=body.note or f"Empty return for {base_trip.trip_no}",
        created_at_utc=now,
    )
    session.add(timeline)

    # Outbox
    for event_name in ("trip.created.v1", "trip.completed.v1"):
        outbox = _create_outbox_event(
            trip,
            event_name,
            {
                "trip_id": trip_id,
                "trip_no": trip.trip_no,
                "source_type": trip.source_type,
                "driver_id": trip.driver_id,
                "vehicle_id": trip.vehicle_id,
                "trailer_id": trip.trailer_id,
                "route_id": trip.route_id,
                "trip_datetime_utc": str(trip.trip_datetime_utc),
                "status": trip.status,
                "enrichment_status": enrichment.enrichment_status,
                "tare_weight_kg": trip.tare_weight_kg,
                "gross_weight_kg": trip.gross_weight_kg,
                "net_weight_kg": trip.net_weight_kg,
                "is_empty_return": trip.is_empty_return,
                "route_status": enrichment.route_status,
            },
        )
        session.add(outbox)

    await session.commit()

    trip = await _get_trip_or_404(session, trip_id)
    resource = _trip_to_resource(trip)
    resource_dict = resource.model_dump(mode="json")

    if idempotency_key:
        await _save_idempotency_record(session, idempotency_key, endpoint_fp, request_hash, 201, resource_dict)
        await session.commit()

    resp = JSONResponse(status_code=201, content=resource_dict)
    resp.headers["ETag"] = make_etag(trip.id, trip.version)
    return resp


# ---------------------------------------------------------------------------
# V8 Section 10.9 — Cancel Trip (Soft Delete)
# ---------------------------------------------------------------------------


@router.post("/api/v1/trips/{trip_id}/cancel")
async def cancel_trip(
    trip_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    x_actor_type: str = Header(..., alias="X-Actor-Type"),
    x_actor_id: str = Header(..., alias="X-Actor-Id"),
) -> Any:
    """V8 Section 10.9 — Cancel (soft delete) with idempotency exception."""
    trip = await _get_trip_or_404(session, trip_id)

    # V8 Section 10.9: If already SOFT_DELETED, return 200 regardless of If-Match
    if trip.status == TripStatus.SOFT_DELETED:
        resource = _trip_to_resource(trip)
        resp = JSONResponse(status_code=200, content=resource.model_dump(mode="json"))
        resp.headers["ETag"] = make_etag(trip.id, trip.version)
        return resp

    # Not yet soft-deleted: enforce If-Match
    parsed = require_if_match(request)
    if parsed[1] != trip.version:
        raise trip_version_mismatch()

    now = _now_utc()
    previous_status = trip.status
    trip.status = TripStatus.SOFT_DELETED
    trip.soft_deleted_at_utc = now
    trip.soft_deleted_by_actor_id = x_actor_id
    trip.version += 1
    trip.updated_at_utc = now

    # Timeline
    timeline = TripTripTimeline(
        id=_generate_id(),
        trip_id=trip_id,
        event_type="TRIP_CANCELLED",
        actor_type=x_actor_type,
        actor_id=x_actor_id,
        note="Trip cancelled (soft deleted)",
        created_at_utc=now,
    )
    session.add(timeline)

    # Outbox: trip.soft_deleted.v1
    outbox = _create_outbox_event(
        trip,
        "trip.soft_deleted.v1",
        {
            "trip_id": trip.id,
            "trip_no": trip.trip_no,
            "previous_status": previous_status,
            "actor_id": x_actor_id,
            "actor_role": x_actor_type,
            "timestamp_utc": str(now),
        },
    )
    session.add(outbox)

    await session.commit()
    trip = await _get_trip_or_404(session, trip_id)
    resource = _trip_to_resource(trip)
    resp = JSONResponse(status_code=200, content=resource.model_dump(mode="json"))
    resp.headers["ETag"] = make_etag(trip.id, trip.version)
    return resp


# ---------------------------------------------------------------------------
# V8 Section 10.10 — Hard Delete Trip
# ---------------------------------------------------------------------------


@router.delete("/api/v1/trips/{trip_id}/hard", status_code=204)
async def hard_delete_trip(
    trip_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    x_actor_type: str = Header(..., alias="X-Actor-Type"),
    x_actor_id: str = Header(..., alias="X-Actor-Id"),
) -> None:
    """V8 Section 10.10 — Physical delete with empty-return child block."""
    trip = await _get_trip_or_404(session, trip_id)
    parsed = require_if_match(request)
    if parsed[1] != trip.version:
        raise trip_version_mismatch()

    # V8: Blocked if trip has empty-return children
    children = await session.execute(select(TripTrip).where(TripTrip.base_trip_id == trip_id))
    if children.scalars().first() is not None:
        raise has_empty_return_child()

    now = _now_utc()

    # Outbox row BEFORE delete (same transaction)
    outbox = _create_outbox_event(
        trip,
        "trip.hard_deleted.v1",
        {
            "trip_id": trip.id,
            "trip_no": trip.trip_no,
            "previous_status": trip.status,
            "actor_id": x_actor_id,
            "actor_role": x_actor_type,
            "timestamp_utc": str(now),
        },
    )
    session.add(outbox)

    # Physical delete (cascades to evidence, enrichment, timeline)
    await session.delete(trip)
    await session.commit()


# ---------------------------------------------------------------------------
# V8 Section 10.18 — Retry Enrichment
# ---------------------------------------------------------------------------


@router.post("/api/v1/trips/{trip_id}/retry-enrichment", status_code=202)
async def retry_enrichment(
    trip_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> RetryEnrichmentResponse:
    """V8 Section 10.18 — Retry enrichment (no If-Match required)."""
    trip = await _get_trip_or_404(session, trip_id)

    if not trip.enrichment:
        # BUG-04: The trip exists; missing enrichment = data integrity error.
        # trip_not_found is misleading here.
        from trip_service.errors import internal_error

        raise internal_error(f"Trip {trip_id} has no enrichment record (data integrity error).")

    # V8: If RUNNING, return 409
    if trip.enrichment.enrichment_status == EnrichmentStatus.RUNNING:
        raise enrichment_already_running()

    now = _now_utc()
    trip.enrichment.claim_token = None
    trip.enrichment.claim_expires_at_utc = None
    trip.enrichment.claimed_by_worker = None
    trip.enrichment.next_retry_at_utc = now
    trip.enrichment.updated_at_utc = now

    await session.commit()

    return RetryEnrichmentResponse(trip_id=trip_id, queued=True)
