"""Trip endpoints aligned to the locked product contract."""

from __future__ import annotations

import json
from datetime import UTC, date
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, select, Select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from trip_service.auth import (
    AuthContext,
    excel_service_auth_dependency,
    reference_service_auth_dependency,
    telegram_service_auth_dependency,
    user_auth_dependency,
)
from trip_service.database import get_session
from trip_service.dependencies import (
    ensure_trip_references_valid,
    fetch_trip_context,
    get_trip_service,
    resolve_route_by_names,
)
from trip_service.enums import (
    ActorType,
    DataQualityFlag,
    EnrichmentStatus,
    EvidenceKind,
    EvidenceSource,
    ReviewReasonCode,
    RouteStatus,
    SourceType,
    TripStatus,
)
from trip_service.errors import (
    enrichment_already_running,
    enrichment_terminal_state,
    hard_delete_requires_soft_deleted,
    has_empty_return_child,
    idempotency_payload_mismatch,
    internal_error,
    trip_forbidden,
    trip_source_reference_conflict,
    trip_version_mismatch,
)
from trip_service.middleware import (
    date_range_to_utc,
    make_etag,
    make_pagination_meta,
    parse_pagination,
    require_trip_if_match,
)
from trip_service.models import (
    TripTrip,
    TripTripDeleteAudit,
    TripTripEnrichment,
    TripTripEvidence,
    TripTripTimeline,
)
from trip_service.schemas import (
    ApproveRequest,
    AssetReferenceCheckRequest,
    AssetReferenceCheckResponse,
    EditTripRequest,
    EmptyReturnRequest,
    ExcelIngestRequest,
    HardDeleteRequest,
    ManualCreateRequest,
    PaginationMeta,
    RejectRequest,
    RetryEnrichmentResponse,
    TelegramFallbackIngestRequest,
    TelegramSlipIngestRequest,
    TimelineItem,
    TimelineResponse,
    TripListResponse,
    TripResource,
)
from trip_service.service import TripService
from trip_service.timezones import local_datetime_to_utc

if TYPE_CHECKING:
    from trip_service.service import TripService
from trip_service.trip_helpers import (
    _REFERENCE_EXCLUDED_STATUSES,
    _check_idempotency_key,
    _coerce_actor_type,
    _compute_data_quality_flag,
    _create_outbox_event,
    _event_payload,
    _generate_id,
    _get_trip_or_404,
    _map_integrity_error,
    _merged_payload_hash,
    _save_idempotency_record,
    apply_trip_context,
    build_delete_audit,
    is_deleted_trip_status,
    normalize_trip_status,
    trip_to_resource,
    utc_now,
)
from trip_service.observability import (
    TRIP_CREATED_TOTAL,
    TRIP_HARD_DELETED_TOTAL,
    get_standard_labels,
)

router = APIRouter(tags=["trips"])

_REFERENCE_ALLOWED_SERVICES = {"driver-service", "fleet-service"}


# _merged_payload_hash is used from trip_helpers instead of local _canonicalize_body.


def _json_response(status_code: int, content: dict[str, Any], headers: dict[str, str] | None = None) -> JSONResponse:
    """Return a JSON response with optional headers."""
    response = JSONResponse(status_code=status_code, content=content)
    for key, value in (headers or {}).items():
        response.headers[key] = value
    return response


def _response_headers_for_trip(trip: TripTrip) -> dict[str, str]:
    """Build the standard response headers for a trip resource."""
    return {
        "ETag": make_etag(trip.id, trip.version),
        "X-Trip-Status": normalize_trip_status(trip.status),
    }


def _require_admin(auth: AuthContext) -> AuthContext:
    """Ensure the current caller is an admin or super admin."""
    authorized_roles = {ActorType.MANAGER.value, ActorType.OPERATOR.value, ActorType.SUPER_ADMIN.value}
    if auth.role not in authorized_roles:
        raise trip_forbidden("User token does not have an admin role.")
    return auth


def _require_super_admin(auth: AuthContext) -> AuthContext:
    """Ensure the current caller is a super admin."""
    if not auth.is_super_admin:
        raise trip_forbidden("Only SUPER_ADMIN can perform this action.")
    return auth


def _require_reference_service_access(auth: AuthContext) -> None:
    """Restrict internal reference endpoints to the known service callers."""
    if auth.role != ActorType.SERVICE.value or auth.service_name not in _REFERENCE_ALLOWED_SERVICES:
        raise trip_forbidden("Service token is not allowed for reference-check endpoints.")


def _apply_status_filter(stmt: Select[Any], status: TripStatus) -> Select[Any]:
    """Apply canonical status filters to the given statement.

    SOFT_DELETED filter also matches legacy 'CANCELLED' rows (prior schema).
    """
    if status == TripStatus.SOFT_DELETED:
        return stmt.where(TripTrip.status.in_([TripStatus.SOFT_DELETED.value, "CANCELLED"]))
    return stmt.where(TripTrip.status == status.value)


def _reference_column_for_asset_type(asset_type: str) -> Any:
    """Map an asset type to the TripTrip ORM column used for active-reference checks."""
    mapping = {
        "DRIVER": TripTrip.driver_id,
        "VEHICLE": TripTrip.vehicle_id,
        "TRAILER": TripTrip.trailer_id,
    }
    return mapping[asset_type]


async def _active_trip_reference_count(
    session: AsyncSession,
    *,
    asset_type: str,
    asset_id: str,
) -> int:
    """Count live and historical non-rejected trips that still reference the given asset."""
    column = _reference_column_for_asset_type(asset_type)
    stmt = (
        select(func.count())
        .select_from(TripTrip)
        .where(
            column == asset_id,
            TripTrip.status.notin_(_REFERENCE_EXCLUDED_STATUSES),
        )
    )
    return int((await session.execute(stmt)).scalar_one())


async def _asset_reference_response(
    session: AsyncSession,
    *,
    asset_type: str,
    asset_id: str,
) -> AssetReferenceCheckResponse:
    """Build the normalized active-reference response payload."""
    active_trip_count = await _active_trip_reference_count(session, asset_type=asset_type, asset_id=asset_id)
    return AssetReferenceCheckResponse(
        asset_type=asset_type,
        asset_id=asset_id,
        is_referenced=active_trip_count > 0,
        active_trip_count=active_trip_count,
    )


def _make_placeholder_trip_no(prefix: str) -> str:
    """Generate a unique placeholder trip number for fallback/minimal imports."""
    return f"{prefix}-{_generate_id()}"


async def _maybe_replay_source_reference(
    session: AsyncSession,
    *,
    source_reference_key: str,
    request_hash: str,
) -> JSONResponse | None:
    """Replay an existing import record when the source reference already exists."""
    existing = (
        await session.execute(select(TripTrip).where(TripTrip.source_reference_key == source_reference_key))
    ).scalar_one_or_none()
    if existing is None:
        return None
    if existing.source_payload_hash != request_hash:
        raise trip_source_reference_conflict(source_reference_key)
    trip = await _get_trip_or_404(session, existing.id)
    resource = trip_to_resource(trip)
    return _json_response(200, resource.model_dump(mode="json"), _response_headers_for_trip(trip))


def _timeline_item_rows(trip: TripTrip) -> TimelineResponse:
    """Map timeline rows into the timeline response contract."""
    items = [
        TimelineItem(
            id=row.id,
            event_type=row.event_type,
            actor_type=row.actor_type,
            actor_id=row.actor_id,
            note=row.note,
            payload_json=json.loads(row.payload_json) if row.payload_json else None,
            created_at_utc=row.created_at_utc,
        )
        for row in sorted(trip.timeline, key=lambda item: item.created_at_utc)
    ]
    return TimelineResponse(items=items)


@router.get("/internal/v1/trips/driver-check/{driver_id}", status_code=200)
async def check_driver_reference(
    driver_id: str,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(reference_service_auth_dependency),
) -> dict[str, Any]:
    """Check if a driver is referenced by any active trips."""
    _require_reference_service_access(auth)
    result = await _asset_reference_response(session, asset_type="DRIVER", asset_id=driver_id)
    return {
        "driver_id": driver_id,
        "is_referenced": result.is_referenced,
        "active_trip_count": result.active_trip_count,
    }


@router.post("/internal/v1/assets/reference-check", status_code=200)
async def check_asset_reference(
    body: AssetReferenceCheckRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(reference_service_auth_dependency),
) -> AssetReferenceCheckResponse:
    """Check whether a driver, vehicle, or trailer is referenced by active trips."""
    _require_reference_service_access(auth)
    return await _asset_reference_response(session, asset_type=body.asset_type, asset_id=body.asset_id)


@router.post("/internal/v1/trips/slips/ingest", status_code=201)
async def ingest_trip_slip(
    body: TelegramSlipIngestRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(telegram_service_auth_dependency),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> Any:
    """Ingest a fully parsed Telegram slip as a pending review trip."""
    request_body = body.model_dump(exclude_none=True)
    request_hash = _merged_payload_hash(request_body)
    endpoint_fp = f"ingest_slip:{body.source_slip_no}"
    replay = await _check_idempotency_key(session, idempotency_key, endpoint_fp, request_hash)
    if replay is not None:
        return replay

    existing_trip = (
        await session.execute(
            select(TripTrip).where(
                TripTrip.source_slip_no == body.source_slip_no,
                TripTrip.source_type == SourceType.TELEGRAM_TRIP_SLIP,
            )
        )
    ).scalar_one_or_none()
    if existing_trip is not None:
        if existing_trip.source_payload_hash != request_hash:
            raise idempotency_payload_mismatch()
        trip = await _get_trip_or_404(session, existing_trip.id)
        resource = trip_to_resource(trip)
        return _json_response(200, resource.model_dump(mode="json"), _response_headers_for_trip(trip))

    replay = await _maybe_replay_source_reference(
        session,
        source_reference_key=body.source_reference_key,
        request_hash=request_hash,
    )
    if replay is not None:
        return replay

    await ensure_trip_references_valid(
        driver_id=body.driver_id,
        vehicle_id=body.vehicle_id,
        trailer_id=body.trailer_id,
    )
    resolution = await resolve_route_by_names(origin_name=body.origin_name, destination_name=body.destination_name)
    context = await fetch_trip_context(resolution.pair_id, field_name="body.origin_name")

    now = utc_now()
    trip_id = _generate_id()
    trip = TripTrip(
        id=trip_id,
        trip_no=body.source_slip_no,
        source_type=SourceType.TELEGRAM_TRIP_SLIP,
        source_slip_no=body.source_slip_no,
        source_reference_key=body.source_reference_key,
        source_payload_hash=request_hash,
        review_reason_code=ReviewReasonCode.SOURCE_IMPORT,
        driver_id=body.driver_id,
        vehicle_id=body.vehicle_id,
        trailer_id=body.trailer_id,
        trip_datetime_utc=local_datetime_to_utc(body.trip_start_local, body.trip_timezone),
        trip_timezone=body.trip_timezone,
        tare_weight_kg=body.tare_weight_kg,
        gross_weight_kg=body.gross_weight_kg,
        net_weight_kg=body.net_weight_kg,
        is_empty_return=False,
        status=TripStatus.PENDING_REVIEW,
        version=1,
        created_by_actor_type=ActorType.SERVICE,
        created_by_actor_id=auth.service_name or auth.actor_id,
        created_at_utc=now,
        updated_at_utc=now,
    )
    apply_trip_context(trip, context, reverse=False)
    session.add(trip)

    session.add(
        TripTripEvidence(
            id=_generate_id(),
            trip_id=trip_id,
            evidence_source=EvidenceSource.TELEGRAM_TRIP_SLIP,
            evidence_kind=EvidenceKind.SLIP_IMAGE,
            source_slip_no=body.source_slip_no,
            telegram_message_id=body.source_reference_key,
            file_key=body.file_key,
            raw_text_ref=body.raw_text_ref,
            ocr_confidence=body.ocr_confidence,
            normalized_truck_plate=body.normalized_truck_plate,
            normalized_trailer_plate=body.normalized_trailer_plate,
            origin_name_raw=body.origin_name,
            destination_name_raw=body.destination_name,
            raw_payload_json=json.dumps(request_body, default=str),
            created_at_utc=now,
        )
    )
    session.add(
        TripTripEnrichment(
            id=_generate_id(),
            trip_id=trip_id,
            enrichment_status=EnrichmentStatus.READY,
            route_status=RouteStatus.READY,
            data_quality_flag=_compute_data_quality_flag(SourceType.TELEGRAM_TRIP_SLIP, body.ocr_confidence, True),
            enrichment_attempt_count=0,
            created_at_utc=now,
            updated_at_utc=now,
        )
    )
    session.add(
        TripTripTimeline(
            id=_generate_id(),
            trip_id=trip_id,
            event_type="TRIP_CREATED",
            actor_type=ActorType.SERVICE.value,
            actor_id=auth.service_name or auth.actor_id,
            note=f"Telegram slip {body.source_slip_no} ingested for review.",
            payload_json=json.dumps({"source_reference_key": body.source_reference_key}),
            created_at_utc=now,
        )
    )
    await _create_outbox_event(session, trip, "trip.created.v1")
    TRIP_CREATED_TOTAL.labels(source_type=trip.source_type, **get_standard_labels()).inc()

    try:
        await session.flush()
        trip = await _get_trip_or_404(session, trip_id)
        resource = trip_to_resource(trip)
        resource_dict = resource.model_dump(mode="json")
        headers = _response_headers_for_trip(trip)
        if idempotency_key:
            await _save_idempotency_record(
                session,
                idempotency_key=idempotency_key,
                endpoint_fingerprint=endpoint_fp,
                request_hash=request_hash,
                response_status=201,
                response_body=resource_dict,
                response_headers=headers,
            )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _map_integrity_error(
            exc,
            trip_no=trip.trip_no,
            source_slip_no=body.source_slip_no,
            source_reference_key=body.source_reference_key,
        ) from exc

    return _json_response(201, resource_dict, headers)


@router.post("/internal/v1/trips/slips/ingest-fallback", status_code=201)
async def ingest_trip_slip_fallback(
    body: TelegramFallbackIngestRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(telegram_service_auth_dependency),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> Any:
    """Create a fallback pending-review trip when Telegram parsing fails."""
    request_hash = _merged_payload_hash(body.model_dump())
    endpoint_fp = f"ingest_fallback:{body.source_reference_key}"
    replay = await _check_idempotency_key(session, idempotency_key, endpoint_fp, request_hash)
    if replay is not None:
        return replay

    existing = await _maybe_replay_source_reference(
        session,
        source_reference_key=body.source_reference_key,
        request_hash=request_hash,
    )
    if existing:
        return existing

    await ensure_trip_references_valid(driver_id=body.driver_id, vehicle_id=None, trailer_id=None)

    now = utc_now()
    trip_id = _generate_id()
    trip = TripTrip(
        id=trip_id,
        trip_no=_make_placeholder_trip_no("TEL"),
        source_type=SourceType.TELEGRAM_TRIP_SLIP,
        source_reference_key=body.source_reference_key,
        source_payload_hash=request_hash,
        review_reason_code=ReviewReasonCode.FALLBACK_MINIMAL,
        driver_id=body.driver_id,
        vehicle_id=None,
        trailer_id=None,
        trip_datetime_utc=body.message_sent_at_utc.astimezone(UTC),
        trip_timezone="UTC",
        tare_weight_kg=None,
        gross_weight_kg=None,
        net_weight_kg=None,
        is_empty_return=False,
        status=TripStatus.PENDING_REVIEW,
        version=1,
        created_by_actor_type=ActorType.SERVICE,
        created_by_actor_id=auth.service_name or auth.actor_id,
        created_at_utc=now,
        updated_at_utc=now,
    )
    session.add(trip)

    session.add(
        TripTripEvidence(
            id=_generate_id(),
            trip_id=trip_id,
            evidence_source=EvidenceSource.TELEGRAM_TRIP_SLIP,
            evidence_kind=EvidenceKind.SLIP_IMAGE,
            telegram_message_id=body.source_reference_key,
            file_key=body.file_key,
            raw_text_ref=body.raw_text_ref,
            raw_payload_json=json.dumps(body.model_dump(exclude_none=True), default=str),
            created_at_utc=now,
        )
    )
    session.add(
        TripTripEnrichment(
            id=_generate_id(),
            trip_id=trip_id,
            enrichment_status=EnrichmentStatus.PENDING,
            route_status=RouteStatus.PENDING,
            data_quality_flag=DataQualityFlag.LOW,
            enrichment_attempt_count=0,
            created_at_utc=now,
            updated_at_utc=now,
        )
    )
    session.add(
        TripTripTimeline(
            id=_generate_id(),
            trip_id=trip_id,
            event_type="TRIP_CREATED",
            actor_type=ActorType.SERVICE.value,
            actor_id=auth.service_name or auth.actor_id,
            note="Fallback Telegram trip created for manual completion.",
            payload_json=json.dumps({"fallback_reason": body.fallback_reason}),
            created_at_utc=now,
        )
    )
    await _create_outbox_event(session, trip, "trip.created.v1")
    TRIP_CREATED_TOTAL.labels(source_type=trip.source_type, **get_standard_labels()).inc()

    try:
        await session.flush()
        trip = await _get_trip_or_404(session, trip_id)
        resource = trip_to_resource(trip)
        resource_dict = resource.model_dump(mode="json")
        headers = _response_headers_for_trip(trip)
        if idempotency_key:
            await _save_idempotency_record(
                session,
                idempotency_key=idempotency_key,
                endpoint_fingerprint=endpoint_fp,
                request_hash=request_hash,
                response_status=201,
                response_body=resource_dict,
                response_headers=headers,
            )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _map_integrity_error(exc, trip_no=trip.trip_no, source_reference_key=body.source_reference_key) from exc

    return _json_response(201, resource_dict, headers)


@router.post("/internal/v1/trips/excel/ingest", status_code=201)
async def ingest_excel_trip(
    body: ExcelIngestRequest,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(excel_service_auth_dependency),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> Any:
    """Ingest a structured Excel row as a pending-review trip."""
    request_hash = _merged_payload_hash(body.model_dump())
    endpoint_fp = f"ingest_excel:{body.source_reference_key}"
    replay = await _check_idempotency_key(session, idempotency_key, endpoint_fp, request_hash)
    if replay is not None:
        return replay

    existing = await _maybe_replay_source_reference(
        session,
        source_reference_key=body.source_reference_key,
        request_hash=request_hash,
    )
    if existing:
        return existing

    await ensure_trip_references_valid(
        driver_id=body.driver_id,
        vehicle_id=body.vehicle_id,
        trailer_id=body.trailer_id,
    )
    context = await fetch_trip_context(body.route_pair_id)
    now = utc_now()
    trip_id = _generate_id()
    trip = TripTrip(
        id=trip_id,
        trip_no=body.trip_no,
        source_type=SourceType.EXCEL_IMPORT,
        source_reference_key=body.source_reference_key,
        source_payload_hash=request_hash,
        review_reason_code=ReviewReasonCode.EXCEL_IMPORT,
        driver_id=body.driver_id,
        vehicle_id=body.vehicle_id,
        trailer_id=body.trailer_id,
        trip_datetime_utc=local_datetime_to_utc(body.trip_start_local, body.trip_timezone),
        trip_timezone=body.trip_timezone,
        tare_weight_kg=body.tare_weight_kg,
        gross_weight_kg=body.gross_weight_kg,
        net_weight_kg=body.net_weight_kg,
        is_empty_return=False,
        status=TripStatus.PENDING_REVIEW,
        version=1,
        created_by_actor_type=ActorType.SERVICE.value,
        created_by_actor_id=auth.service_name or auth.actor_id,
        created_at_utc=now,
        updated_at_utc=now,
    )
    apply_trip_context(trip, context, reverse=False)
    session.add(trip)
    session.add(
        TripTripEvidence(
            id=_generate_id(),
            trip_id=trip_id,
            evidence_source=EvidenceSource.EXCEL_IMPORT,
            evidence_kind=EvidenceKind.IMPORT_ROW,
            row_number=body.row_number,
            raw_payload_json=json.dumps(body.model_dump(exclude_none=True), default=str),
            created_at_utc=now,
        )
    )
    session.add(
        TripTripEnrichment(
            id=_generate_id(),
            trip_id=trip_id,
            enrichment_status=EnrichmentStatus.READY,
            route_status=RouteStatus.READY,
            data_quality_flag=DataQualityFlag.HIGH,
            enrichment_attempt_count=0,
            created_at_utc=now,
            updated_at_utc=now,
        )
    )
    session.add(
        TripTripTimeline(
            id=_generate_id(),
            trip_id=trip_id,
            event_type="TRIP_CREATED",
            actor_type=ActorType.SERVICE.value,
            actor_id=auth.service_name or auth.actor_id,
            note="Excel row ingested for review.",
            payload_json=json.dumps({"source_reference_key": body.source_reference_key, "row_number": body.row_number}),
            created_at_utc=now,
        )
    )
    await _create_outbox_event(session, trip, "trip.created.v1")
    TRIP_CREATED_TOTAL.labels(source_type=trip.source_type, **get_standard_labels()).inc()

    try:
        await session.flush()
        trip = await _get_trip_or_404(session, trip_id)
        resource = trip_to_resource(trip)
        resource_dict = resource.model_dump(mode="json")
        headers = _response_headers_for_trip(trip)
        if idempotency_key:
            await _save_idempotency_record(
                session,
                idempotency_key=idempotency_key,
                endpoint_fingerprint=endpoint_fp,
                request_hash=request_hash,
                response_status=201,
                response_body=resource_dict,
                response_headers=headers,
            )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _map_integrity_error(
            exc,
            trip_no=body.trip_no,
            source_reference_key=body.source_reference_key,
        ) from exc

    return _json_response(201, resource_dict, headers)


@router.get("/internal/v1/trips/excel/export-feed", response_model=TripListResponse)
async def excel_export_feed(
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(excel_service_auth_dependency),
    status: TripStatus | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    timezone: str = Query("Europe/Istanbul"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
) -> TripListResponse:
    """Return structured trip rows for the separate Excel service."""
    del auth
    pagination = parse_pagination(page, per_page)
    _deleted_statuses = [TripStatus.SOFT_DELETED.value, "CANCELLED"]
    stmt = (
        select(TripTrip)
        .options(selectinload(TripTrip.enrichment), selectinload(TripTrip.evidence))
        .where(TripTrip.status.not_in(_deleted_statuses))
    )
    if status is not None:
        stmt = _apply_status_filter(stmt, status)
    if date_from or date_to:
        utc_from, utc_to = date_range_to_utc(date_from, date_to, timezone)
        if utc_from is not None:
            stmt = stmt.where(TripTrip.trip_datetime_utc >= utc_from)
        if utc_to is not None:
            stmt = stmt.where(TripTrip.trip_datetime_utc < utc_to)

    total_items = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    trips = (
        (
            await session.execute(
                stmt.order_by(TripTrip.trip_datetime_utc.desc(), TripTrip.id.desc())
                .offset(pagination.offset)
                .limit(pagination.per_page)
            )
        )
        .scalars()
        .all()
    )
    return TripListResponse(
        items=[trip_to_resource(trip) for trip in trips],
        meta=PaginationMeta(
            **make_pagination_meta(
                pagination.page,
                pagination.per_page,
                total_items,
                sort="trip_datetime_utc_desc,id_desc",
            )
        ),
    )


@router.post(
    "/api/v1/trips",
    response_model=TripResource,
    status_code=201,
    summary="Create a new trip",
)
async def create_trip(
    body: ManualCreateRequest,
    service: TripService = Depends(get_trip_service),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    legacy_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
) -> Any:
    """Create a manual trip using route-pair context instead of raw route ids."""
    resource_dict, headers = await service.create_trip(
        body=body,
        idempotency_key=idempotency_key,
        legacy_idempotency_key=legacy_idempotency_key,
    )
    return _json_response(201, resource_dict, headers)


@router.get("/api/v1/trips", response_model=TripListResponse)
async def list_trips(
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(user_auth_dependency),
    status: TripStatus | None = Query(None),
    source_type: SourceType | None = Query(None),
    driver_id: str | None = Query(None, min_length=1),
    include_empty_returns: bool = Query(True),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    timezone: str = Query("Europe/Istanbul"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
) -> TripListResponse:
    """Return the admin trip list for Tauri screens."""
    del auth
    pagination = parse_pagination(page, per_page)
    stmt = select(TripTrip).options(selectinload(TripTrip.enrichment), selectinload(TripTrip.evidence))
    if status is not None:
        stmt = _apply_status_filter(stmt, status)
    else:
        stmt = stmt.where(TripTrip.status.notin_([TripStatus.SOFT_DELETED.value, "CANCELLED"]))
    if source_type is not None:
        stmt = stmt.where(TripTrip.source_type == source_type)
    if driver_id is not None:
        stmt = stmt.where(TripTrip.driver_id == driver_id)
    if not include_empty_returns:
        stmt = stmt.where(TripTrip.is_empty_return.is_(False))
    if date_from or date_to:
        utc_from, utc_to = date_range_to_utc(date_from, date_to, timezone)
        if utc_from is not None:
            stmt = stmt.where(TripTrip.trip_datetime_utc >= utc_from)
        if utc_to is not None:
            stmt = stmt.where(TripTrip.trip_datetime_utc < utc_to)

    total_items = (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    trips = (
        (
            await session.execute(
                stmt.order_by(TripTrip.trip_datetime_utc.desc(), TripTrip.id.desc())
                .offset(pagination.offset)
                .limit(pagination.per_page)
            )
        )
        .scalars()
        .all()
    )

    return TripListResponse(
        items=[trip_to_resource(trip) for trip in trips],
        meta=PaginationMeta(
            **make_pagination_meta(
                pagination.page,
                pagination.per_page,
                total_items,
                sort="trip_datetime_utc_desc,id_desc",
            )
        ),
    )


@router.get("/api/v1/trips/{trip_id}", response_model=TripResource)
async def get_trip(
    trip_id: str,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(user_auth_dependency),
) -> Any:
    """Return a single trip resource with ETag."""
    del auth
    trip = await _get_trip_or_404(session, trip_id)
    resource = trip_to_resource(trip)
    return _json_response(200, resource.model_dump(mode="json"), _response_headers_for_trip(trip))


@router.get("/api/v1/trips/{trip_id}/timeline", response_model=TimelineResponse)
async def get_trip_timeline(
    trip_id: str,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(user_auth_dependency),
) -> TimelineResponse:
    """Return a trip timeline ordered oldest to newest."""
    del auth
    trip = await _get_trip_or_404(session, trip_id)
    return _timeline_item_rows(trip)


@router.patch("/api/v1/trips/{trip_id}", response_model=TripResource)
async def edit_trip(
    trip_id: str,
    body: EditTripRequest,
    request: Request,
    service: TripService = Depends(get_trip_service),
) -> Any:
    """Edit trip fields using the centralized TripService layer."""
    if_match = request.headers.get("If-Match")
    resource_dict, headers = await service.edit_trip(
        trip_id=trip_id,
        body=body,
        if_match=if_match,
    )
    return _json_response(200, resource_dict, headers)


@router.post("/api/v1/trips/{trip_id}/approve", response_model=TripResource)
async def approve_trip(
    trip_id: str,
    body: ApproveRequest,
    request: Request,
    service: TripService = Depends(get_trip_service),
) -> Any:
    """Approve a pending-review trip once it is complete and conflict free."""
    if_match = request.headers.get("If-Match")
    resource_dict, headers = await service.approve_trip(
        trip_id=trip_id,
        body=body,
        if_match=if_match,
    )
    return _json_response(200, resource_dict, headers)


@router.post("/api/v1/trips/{trip_id}/reject", response_model=TripResource)
async def reject_trip(
    trip_id: str,
    body: RejectRequest,
    request: Request,
    service: TripService = Depends(get_trip_service),
) -> Any:
    """Reject a pending-review trip using the centralized service."""
    if_match = request.headers.get("If-Match")
    resource_dict, headers = await service.reject_trip(
        trip_id=trip_id,
        body=body,
        if_match=if_match,
    )
    return _json_response(200, resource_dict, headers)


@router.post("/api/v1/trips/{base_trip_id}/empty-return", response_model=TripResource, status_code=201)
async def create_empty_return(
    base_trip_id: str,
    body: EmptyReturnRequest,
    request: Request,
    service: TripService = Depends(get_trip_service),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> Any:
    """Create a reverse derived empty-return trip from a completed base trip."""
    # if_match is not used by create_empty_return in service layer
    _ = request.headers.get("If-Match")
    resource_dict, headers = await service.create_empty_return(
        base_trip_id=base_trip_id,
        body=body,
        idempotency_key=idempotency_key,
    )
    return _json_response(201, resource_dict, headers)


@router.post("/api/v1/trips/{trip_id}/cancel", response_model=TripResource)
async def cancel_trip(
    trip_id: str,
    request: Request,
    service: TripService = Depends(get_trip_service),
) -> Any:
    """Soft-delete a trip under the TASK-0033 contract."""
    if_match = request.headers.get("If-Match")
    resource_dict, headers = await service.cancel_trip(trip_id=trip_id, if_match=if_match)
    return _json_response(200, resource_dict, headers)


@router.post("/api/v1/trips/{trip_id}/hard-delete", status_code=204)
async def hard_delete_trip(
    trip_id: str,
    body: HardDeleteRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(user_auth_dependency),
) -> Response:
    """Hard-delete a soft-deleted trip after writing an immutable audit row."""
    auth = _require_super_admin(_require_admin(auth))
    current_version = require_trip_if_match(request, trip_id)
    trip = await _get_trip_or_404(session, trip_id)
    if current_version != trip.version:
        raise trip_version_mismatch()
    if not is_deleted_trip_status(trip.status):
        raise hard_delete_requires_soft_deleted()
    if trip.empty_return_children:
        raise has_empty_return_child()

    now = utc_now()
    audit_row: TripTripDeleteAudit = build_delete_audit(
        audit_id=_generate_id(),
        trip=trip,
        actor_id=auth.actor_id,
        actor_role=_coerce_actor_type(auth.role),
        reason=body.reason,
        deleted_at_utc=now,
    )
    session.add(audit_row)
    await _create_outbox_event(session, trip, "trip.hard_deleted.v1", {"reason": body.reason, **_event_payload(trip)})
    TRIP_HARD_DELETED_TOTAL.labels(**get_standard_labels()).inc()
    await session.delete(trip)
    await session.commit()
    return Response(status_code=204)


@router.post("/api/v1/trips/{trip_id}/retry-enrichment", response_model=RetryEnrichmentResponse, status_code=202)
async def retry_enrichment(
    trip_id: str,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(user_auth_dependency),
) -> RetryEnrichmentResponse:
    """Manually re-queue enrichment for a non-terminal enrichment row."""
    del auth
    trip = await _get_trip_or_404(session, trip_id)
    if trip.enrichment is None:
        raise internal_error(f"Trip {trip_id} has no enrichment record.")

    now = utc_now()
    if trip.enrichment.enrichment_status == EnrichmentStatus.RUNNING and (
        trip.enrichment.claim_expires_at_utc is None or trip.enrichment.claim_expires_at_utc > now
    ):
        raise enrichment_already_running()
    if trip.enrichment.enrichment_status in (EnrichmentStatus.READY, EnrichmentStatus.SKIPPED):
        raise enrichment_terminal_state()

    trip.enrichment.enrichment_status = EnrichmentStatus.PENDING
    trip.enrichment.route_status = RouteStatus.READY if trip.route_id else RouteStatus.PENDING
    trip.enrichment.enrichment_attempt_count = 0
    trip.enrichment.claim_token = None
    trip.enrichment.claim_expires_at_utc = None
    trip.enrichment.claimed_by_worker = None
    trip.enrichment.last_enrichment_error_code = None
    trip.enrichment.next_retry_at_utc = now
    trip.enrichment.updated_at_utc = now
    await session.commit()

    return RetryEnrichmentResponse(trip_id=trip_id, queued=True)
