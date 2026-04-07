"""Trip endpoints aligned to the locked product contract."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from ulid import ULID

from trip_service.auth import (
    AuthContext,
    excel_service_auth_dependency,
    reference_service_auth_dependency,
    telegram_service_auth_dependency,
    user_auth_dependency,
)
from trip_service.config import settings
from trip_service.database import get_session
from trip_service.dependencies import ensure_trip_references_valid, fetch_trip_context, resolve_route_by_names
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
    empty_return_already_exists,
    enrichment_already_running,
    enrichment_terminal_state,
    hard_delete_requires_soft_deleted,
    has_empty_return_child,
    idempotency_payload_mismatch,
    internal_error,
    invalid_base_for_empty_return,
    invalid_status_transition,
    route_required_for_completion,
    source_slip_conflict,
    trip_change_reason_required,
    trip_forbidden,
    trip_no_conflict,
    trip_source_locked_field,
    trip_source_reference_conflict,
    trip_validation_error,
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
    TripIdempotencyRecord,
    TripTrip,
    TripTripDeleteAudit,
    TripTripEnrichment,
    TripTripEvidence,
    TripTripTimeline,
)
from trip_service.observability import (
    TRIP_CANCELLED_TOTAL,
    TRIP_COMPLETED_TOTAL,
    TRIP_CREATED_TOTAL,
    TRIP_HARD_DELETED_TOTAL,
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
    RejectRequest,
    RetryEnrichmentResponse,
    TelegramFallbackIngestRequest,
    TelegramSlipIngestRequest,
    TimelineItem,
    TimelineResponse,
    TripListResponse,
    TripResource,
)
from trip_service.timezones import local_datetime_to_utc
from trip_service.trip_helpers import (
    _check_idempotency_key,
    _classify_manual_status,
    _create_outbox_event,
    _ensure_complete_for_completion,
    _event_payload,
    _get_trip_or_404,
    _merged_payload_hash,
    _write_audit,
    _write_outbox,
    apply_trip_context,
    assert_no_trip_overlap,
    build_delete_audit,
    get_standard_labels,
    is_deleted_trip_status,
    normalize_trip_status,
    serialize_trip_admin,
    transition_trip,
    trip_to_resource,
    utc_now,
)

router = APIRouter(tags=["trips"])

_REFERENCE_ALLOWED_SERVICES = {"driver-service", "fleet-service"}
_REFERENCE_EXCLUDED_STATUSES = (
    TripStatus.REJECTED.value,
    TripStatus.SOFT_DELETED.value,
)


def _generate_id() -> str:
    """Generate a ULID string for primary keys."""
    return str(ULID())


def _canonicalize_body(body: dict[str, Any]) -> str:
    """SHA-256 of a canonicalized request body."""
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _json_response(status_code: int, content: dict[str, Any], headers: dict[str, str] | None = None) -> JSONResponse:
    """Return a JSON response with optional headers."""
    response = JSONResponse(status_code=status_code, content=content)
    for key, value in (headers or {}).items():
        response.headers[key] = value
    return response


def _response_headers_for_trip(trip: TripTrip) -> dict[str, str]:
    """Build the standard response headers for a trip resource."""
    return {"ETag": make_etag(trip.id, trip.version)}


def _resolve_idempotency_key(canonical_key: str | None, legacy_key: str | None) -> str | None:
    """Prefer the canonical idempotency header while still accepting the legacy alias."""
    return canonical_key or legacy_key


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


def _validate_trip_weights(tare_weight_kg: int | None, gross_weight_kg: int | None, net_weight_kg: int | None) -> None:
    """Validate weight invariants before hitting database constraints."""
    if tare_weight_kg is None or gross_weight_kg is None or net_weight_kg is None:
        return
    errors: list[dict[str, str]] = []
    if gross_weight_kg < tare_weight_kg:
        errors.append({"field": "body.gross_weight_kg", "message": "gross_weight_kg must be >= tare_weight_kg."})
    if net_weight_kg != gross_weight_kg - tare_weight_kg:
        errors.append(
            {"field": "body.net_weight_kg", "message": "net_weight_kg must equal gross_weight_kg - tare_weight_kg."}
        )
    if errors:
        raise trip_validation_error("Trip weights are inconsistent.", errors=errors)


def _compute_data_quality_flag(source_type: str, ocr_confidence: float | None, route_resolved: bool) -> str:
    """Compute the trip data-quality flag using the locked source contract."""
    if source_type in (SourceType.ADMIN_MANUAL, SourceType.EMPTY_RETURN_ADMIN, SourceType.EXCEL_IMPORT):
        return DataQualityFlag.HIGH
    if ocr_confidence is not None and ocr_confidence >= 0.90 and route_resolved:
        return DataQualityFlag.HIGH
    if ocr_confidence is not None and ocr_confidence >= 0.70:
        return DataQualityFlag.MEDIUM
    if not route_resolved:
        return DataQualityFlag.MEDIUM
    return DataQualityFlag.LOW


def _constraint_name(exc: IntegrityError) -> str:
    """Extract a stable constraint/index name from an IntegrityError."""
    original = getattr(exc, "orig", None)
    if original is None:
        return str(exc)
    if getattr(original, "constraint_name", None):
        return str(original.constraint_name)
    if getattr(getattr(original, "diag", None), "constraint_name", None):
        return str(original.diag.constraint_name)
    return str(original)


def _map_integrity_error(
    exc: IntegrityError,
    *,
    trip_no: str | None = None,
    source_slip_no: str | None = None,
    source_reference_key: str | None = None,
) -> Exception:
    """Map database integrity errors to stable problem responses."""
    name = _constraint_name(exc)
    if "uq_trip_trips_trip_no" in name:
        return trip_no_conflict(trip_no or "unknown")
    if "uq_trips_source_slip_no_telegram" in name:
        return source_slip_conflict(source_slip_no or "unknown")
    if "uq_trips_source_reference_key" in name:
        return trip_source_reference_conflict(source_reference_key or "unknown")
    if "uq_trips_empty_return_base_trip" in name:
        return empty_return_already_exists()
    return internal_error(f"Database integrity error: {name}")


def _coerce_actor_type(role: str) -> str:
    """Normalize role strings for persistence/audit fields."""
    return str(role)


def _apply_status_filter(stmt, status: TripStatus):  # noqa: ANN001
    """Apply canonical status filters to the given statement.

    SOFT_DELETED filter also matches legacy 'CANCELLED' rows (prior schema).
    """
    if status == TripStatus.SOFT_DELETED:
        return stmt.where(TripTrip.status.in_([TripStatus.SOFT_DELETED.value, "CANCELLED"]))
    return stmt.where(TripTrip.status == status.value)


def _reference_column_for_asset_type(asset_type: str):  # noqa: ANN001
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


async def _save_idempotency_record(
    session: AsyncSession,
    *,
    idempotency_key: str,
    endpoint_fingerprint: str,
    request_hash: str,
    response_status: int,
    response_body: dict[str, Any],
    response_headers: dict[str, str],
) -> None:
    """Persist idempotency replay material for later requests."""
    now = utc_now()
    stmt = (
        pg_insert(TripIdempotencyRecord)
        .values(
            idempotency_key=idempotency_key,
            endpoint_fingerprint=endpoint_fingerprint,
            request_hash=request_hash,
            response_status=response_status,
            response_headers_json=response_headers,
            response_body_json=json.dumps(response_body, default=str),
            created_at_utc=now,
            expires_at_utc=now + timedelta(hours=settings.idempotency_retention_hours),
        )
        .on_conflict_do_update(
            index_elements=["idempotency_key", "endpoint_fingerprint"],
            set_={
                "request_hash": request_hash,
                "response_status": response_status,
                "response_headers_json": response_headers,
                "response_body_json": json.dumps(response_body, default=str),
                "expires_at_utc": now + timedelta(hours=settings.idempotency_retention_hours),
            },
        )
    )
    await session.execute(stmt)


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


# Redundant local definition removed. Using trip_helpers implementation.


def _set_enrichment_state(
    trip: TripTrip,
    enrichment: TripTripEnrichment,
    *,
    source_type: str,
    route_ready: bool,
    ocr_confidence: float | None = None,
) -> None:
    """Synchronize enrichment fields with the current trip payload completeness."""
    enrichment.route_status = RouteStatus.READY if route_ready else RouteStatus.PENDING
    enrichment.enrichment_status = EnrichmentStatus.READY if route_ready else EnrichmentStatus.PENDING
    enrichment.data_quality_flag = _compute_data_quality_flag(source_type, ocr_confidence, route_resolved=route_ready)
    enrichment.claim_token = None
    enrichment.claim_expires_at_utc = None
    enrichment.claimed_by_worker = None
    enrichment.last_enrichment_error_code = None
    enrichment.next_retry_at_utc = None
    enrichment.updated_at_utc = utc_now()


def _maybe_require_change_reason(
    auth: AuthContext,
    body: EditTripRequest,
    trip: TripTrip,
    new_driver_id: str | None,
) -> None:
    """Enforce source-aware driver edit rules for imported trips."""
    if new_driver_id is None or new_driver_id == trip.driver_id:
        return
    if trip.source_type not in {SourceType.TELEGRAM_TRIP_SLIP, SourceType.EXCEL_IMPORT}:
        return
    if auth.is_super_admin:
        if not body.change_reason or not body.change_reason.strip():
            raise trip_change_reason_required("SUPER_ADMIN must provide change_reason to reassign imported driver.")
        return
    raise trip_source_locked_field("ADMIN cannot change driver_id on imported trips.")


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
    request_body = body.model_dump(exclude_none=True, mode="json")
    request_hash = _merged_payload_hash(request_body)
    endpoint_fp = f"ingest_fallback:{body.source_reference_key}"
    replay = await _check_idempotency_key(session, idempotency_key, endpoint_fp, request_hash)
    if replay is not None:
        return replay

    replay = await _maybe_replay_source_reference(
        session,
        source_reference_key=body.source_reference_key,
        request_hash=request_hash,
    )
    if replay is not None:
        return replay

    await ensure_trip_references_valid(driver_id=body.driver_id, vehicle_id=None, trailer_id=None)

    now = utc_now()
    trip_id = _generate_id()
    trip = TripTrip(
        id=trip_id,
        trip_no=_make_placeholder_trip_no("TG-FALLBACK"),
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
            raw_payload_json=json.dumps(request_body, default=str),
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
    request_body = body.model_dump(exclude_none=True)
    request_hash = _merged_payload_hash(request_body)
    endpoint_fp = f"ingest_excel:{body.source_reference_key}"
    replay = await _check_idempotency_key(session, idempotency_key, endpoint_fp, request_hash)
    if replay is not None:
        return replay

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
        meta=make_pagination_meta(
            pagination.page,
            pagination.per_page,
            total_items,
            sort="trip_datetime_utc_desc,id_desc",
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
    auth: AuthContext = Depends(user_auth_dependency),
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    legacy_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
):
    """Create a manual trip using route-pair context instead of raw route ids."""
    auth = _require_admin(auth)
    effective_idempotency_key = _resolve_idempotency_key(idempotency_key, legacy_idempotency_key)
    request_body = body.model_dump(exclude_none=True)
    request_hash = _merged_payload_hash(request_body)
    endpoint_fp = f"create_trip:{auth.actor_id}"
    replay = await _check_idempotency_key(session, effective_idempotency_key, endpoint_fp, request_hash)
    if replay is not None:
        return replay

    await ensure_trip_references_valid(
        driver_id=body.driver_id,
        vehicle_id=body.vehicle_id,
        trailer_id=body.trailer_id,
    )
    context = await fetch_trip_context(body.route_pair_id)
    trip_start_utc = local_datetime_to_utc(body.trip_start_local, body.trip_timezone)
    status, review_reason = await _classify_manual_status(auth, trip_start_utc)
    now = utc_now()
    trip_id = _generate_id()
    trip = TripTrip(
        id=trip_id,
        trip_no=body.trip_no,
        source_type=SourceType.ADMIN_MANUAL,
        review_reason_code=review_reason,
        source_payload_hash=request_hash,
        driver_id=body.driver_id,
        vehicle_id=body.vehicle_id,
        trailer_id=body.trailer_id,
        trip_datetime_utc=trip_start_utc,
        trip_timezone=body.trip_timezone,
        tare_weight_kg=body.tare_weight_kg,
        gross_weight_kg=body.gross_weight_kg,
        net_weight_kg=body.net_weight_kg,
        is_empty_return=False,
        status=status,
        version=1,
        created_by_actor_type=_coerce_actor_type(auth.role),
        created_by_actor_id=auth.actor_id,
        created_at_utc=now,
        updated_at_utc=now,
    )
    apply_trip_context(trip, context, reverse=False)
    await assert_no_trip_overlap(
        session,
        driver_id=trip.driver_id,
        vehicle_id=trip.vehicle_id,
        trailer_id=trip.trailer_id,
        trip_start_utc=trip.trip_datetime_utc,
        planned_end_utc=trip.planned_end_utc or trip.trip_datetime_utc,
    )
    session.add(trip)
    session.add(
        TripTripEvidence(
            id=_generate_id(),
            trip_id=trip_id,
            evidence_source=EvidenceSource.ADMIN_MANUAL,
            evidence_kind=EvidenceKind.MANUAL_ENTRY,
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
            actor_type=_coerce_actor_type(auth.role),
            actor_id=auth.actor_id,
            note=body.note or "Manual trip created.",
            payload_json=json.dumps({"route_pair_id": body.route_pair_id}),
            created_at_utc=now,
        )
    )
    await _create_outbox_event(session, trip, "trip.created.v1")
    TRIP_CREATED_TOTAL.labels(source_type=trip.source_type, **get_standard_labels()).inc()
    if trip.status == TripStatus.COMPLETED:
        await _create_outbox_event(session, trip, "trip.completed.v1")
        TRIP_COMPLETED_TOTAL.labels(**get_standard_labels()).inc()

    try:
        await session.flush()
        trip = await _get_trip_or_404(session, trip_id)
        resource = trip_to_resource(trip)
        resource_dict = resource.model_dump(mode="json")
        headers = _response_headers_for_trip(trip)
        if effective_idempotency_key:
            await _save_idempotency_record(
                session,
                idempotency_key=effective_idempotency_key,
                endpoint_fingerprint=endpoint_fp,
                request_hash=request_hash,
                response_status=201,
                response_body=resource_dict,
                response_headers=headers,
            )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _map_integrity_error(exc, trip_no=body.trip_no) from exc

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
        stmt = stmt.where(TripTrip.status.not_in([TripStatus.SOFT_DELETED.value, "CANCELLED"]))
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
        meta=make_pagination_meta(
            pagination.page,
            pagination.per_page,
            total_items,
            sort="trip_datetime_utc_desc,id_desc",
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
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(user_auth_dependency),
) -> Any:
    """Edit trip fields under the source-aware product contract."""
    auth = _require_admin(auth)
    current_version = require_trip_if_match(request, trip_id)
    trip = await _get_trip_or_404(session, trip_id)
    if current_version != trip.version:
        raise trip_version_mismatch()
    normalized_status = normalize_trip_status(trip.status)
    if normalized_status not in {TripStatus.PENDING_REVIEW.value, TripStatus.COMPLETED.value}:
        raise invalid_status_transition(f"Cannot edit trip in {normalized_status} state.")

    old_snapshot = serialize_trip_admin(trip)
    update_data = body.model_dump(exclude_unset=True)

    _maybe_require_change_reason(auth, body, trip, update_data.get("driver_id"))

    candidate_driver_id = update_data.get("driver_id", trip.driver_id)
    candidate_vehicle_id = update_data.get("vehicle_id", trip.vehicle_id)
    candidate_trailer_id = update_data.get("trailer_id", trip.trailer_id)
    if {"driver_id", "vehicle_id", "trailer_id"} & update_data.keys():
        await ensure_trip_references_valid(
            driver_id=candidate_driver_id,
            vehicle_id=candidate_vehicle_id,
            trailer_id=candidate_trailer_id,
        )

    candidate_tare = update_data.get("tare_weight_kg", trip.tare_weight_kg)
    candidate_gross = update_data.get("gross_weight_kg", trip.gross_weight_kg)
    candidate_net = update_data.get("net_weight_kg", trip.net_weight_kg)
    if {"tare_weight_kg", "gross_weight_kg", "net_weight_kg"} & update_data.keys():
        _validate_trip_weights(candidate_tare, candidate_gross, candidate_net)

    changed_fields: list[str] = []
    now = utc_now()

    if "trip_start_local" in update_data or "trip_timezone" in update_data:
        timezone_value = update_data.get("trip_timezone", trip.trip_timezone)
        if "trip_start_local" in update_data:
            new_trip_start_utc = local_datetime_to_utc(update_data["trip_start_local"], timezone_value)
            if new_trip_start_utc != trip.trip_datetime_utc:
                trip.trip_datetime_utc = new_trip_start_utc
                changed_fields.append("trip_datetime_utc")
        if "trip_timezone" in update_data and update_data["trip_timezone"] != trip.trip_timezone:
            trip.trip_timezone = update_data["trip_timezone"]
            changed_fields.append("trip_timezone")

    for field_name in ("driver_id", "vehicle_id", "trailer_id", "tare_weight_kg", "gross_weight_kg", "net_weight_kg"):
        if field_name in update_data and getattr(trip, field_name) != update_data[field_name]:
            setattr(trip, field_name, update_data[field_name])
            changed_fields.append(field_name)

    if "route_pair_id" in update_data and update_data["route_pair_id"] != trip.route_pair_id:
        context = await fetch_trip_context(update_data["route_pair_id"])
        apply_trip_context(trip, context, reverse=trip.is_empty_return)
        changed_fields.append("route_pair_id")
    elif "trip_start_local" in update_data or "trip_timezone" in update_data:
        if trip.route_pair_id is not None:
            context = await fetch_trip_context(trip.route_pair_id)
            apply_trip_context(trip, context, reverse=trip.is_empty_return)

    if update_data.get("note") is not None:
        changed_fields.append("note")

    if not changed_fields:
        resource = trip_to_resource(trip)
        return _json_response(200, resource.model_dump(mode="json"), _response_headers_for_trip(trip))

    if trip.status == TripStatus.COMPLETED or trip.source_type in (
        SourceType.ADMIN_MANUAL,
        SourceType.EMPTY_RETURN_ADMIN,
        SourceType.EXCEL_IMPORT,
    ):
        _ensure_complete_for_completion(trip)

    overlap_fields = {"driver_id", "vehicle_id", "trailer_id", "trip_datetime_utc", "route_pair_id"}
    if overlap_fields & set(changed_fields) and trip.planned_end_utc is not None:
        await assert_no_trip_overlap(
            session,
            driver_id=trip.driver_id,
            vehicle_id=trip.vehicle_id,
            trailer_id=trip.trailer_id,
            trip_start_utc=trip.trip_datetime_utc,
            planned_end_utc=trip.planned_end_utc,
            exclude_trip_id=trip.id,
        )

    if trip.enrichment is not None:
        _set_enrichment_state(
            trip,
            trip.enrichment,
            source_type=trip.source_type,
            route_ready=trip.route_id is not None and trip.planned_end_utc is not None,
        )

    trip.version += 1
    trip.updated_at_utc = now

    new_snapshot = serialize_trip_admin(trip)

    await _write_audit(
        session,
        trip_id=trip.id,
        action_type="UPDATE",
        actor_id=auth.actor_id,
        actor_role=str(auth.role),
        old_snapshot=old_snapshot,
        new_snapshot=new_snapshot,
        changed_fields=changed_fields,
        reason=body.change_reason or f"Fields changed: {', '.join(changed_fields)}",
        request_id=request.headers.get("X-Request-ID"),
    )

    session.add(
        TripTripTimeline(
            id=_generate_id(),
            trip_id=trip.id,
            event_type="TRIP_EDITED",
            actor_type=_coerce_actor_type(auth.role),
            actor_id=auth.actor_id,
            note=body.note or f"Fields changed: {', '.join(changed_fields)}",
            payload_json=json.dumps({"changed_fields": changed_fields, "change_reason": body.change_reason}),
            created_at_utc=now,
        )
    )
    # Use the new outbox helper
    await _write_outbox(session, trip_id=trip.id, event_name="trip.edited.v1", payload=_event_payload(trip))

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _map_integrity_error(exc, trip_no=trip.trip_no, source_reference_key=trip.source_reference_key) from exc

    trip = await _get_trip_or_404(session, trip.id)
    resource = trip_to_resource(trip)
    return _json_response(200, resource.model_dump(mode="json"), _response_headers_for_trip(trip))


@router.post("/api/v1/trips/{trip_id}/approve", response_model=TripResource)
async def approve_trip(
    trip_id: str,
    body: ApproveRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(user_auth_dependency),
) -> Any:
    """Approve a pending-review trip once it is complete and conflict free."""
    auth = _require_admin(auth)
    current_version = require_trip_if_match(request, trip_id)
    trip = await _get_trip_or_404(session, trip_id)
    if current_version != trip.version:
        raise trip_version_mismatch()
    if normalize_trip_status(trip.status) != TripStatus.PENDING_REVIEW.value:
        raise invalid_status_transition("Only PENDING_REVIEW trips can be approved.")
    _ensure_complete_for_completion(trip)
    if trip.route_id is None or trip.planned_end_utc is None:
        raise route_required_for_completion()

    await assert_no_trip_overlap(
        session,
        driver_id=trip.driver_id,
        vehicle_id=trip.vehicle_id,
        trailer_id=trip.trailer_id,
        trip_start_utc=trip.trip_datetime_utc,
        planned_end_utc=trip.planned_end_utc,
        exclude_trip_id=trip.id,
    )

    transition_trip(trip, TripStatus.COMPLETED)
    if trip.enrichment is not None:
        _set_enrichment_state(
            trip,
            trip.enrichment,
            source_type=trip.source_type,
            route_ready=True,
        )

    now = utc_now()
    session.add(
        TripTripTimeline(
            id=_generate_id(),
            trip_id=trip.id,
            event_type="TRIP_APPROVED",
            actor_type=_coerce_actor_type(auth.role),
            actor_id=auth.actor_id,
            note=body.note or "Trip approved.",
            created_at_utc=now,
        )
    )
    await _create_outbox_event(session, trip, "trip.completed.v1")
    TRIP_COMPLETED_TOTAL.inc()
    await session.commit()

    trip = await _get_trip_or_404(session, trip.id)
    resource = trip_to_resource(trip)
    return _json_response(200, resource.model_dump(mode="json"), _response_headers_for_trip(trip))


@router.post("/api/v1/trips/{trip_id}/reject", response_model=TripResource)
async def reject_trip(
    trip_id: str,
    body: RejectRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(user_auth_dependency),
) -> Any:
    """Reject a pending-review trip."""
    auth = _require_admin(auth)
    current_version = require_trip_if_match(request, trip_id)
    trip = await _get_trip_or_404(session, trip_id)
    if current_version != trip.version:
        raise trip_version_mismatch()
    if normalize_trip_status(trip.status) != TripStatus.PENDING_REVIEW.value:
        raise invalid_status_transition("Only PENDING_REVIEW trips can be rejected.")

    now = utc_now()
    transition_trip(trip, TripStatus.REJECTED)
    session.add(
        TripTripTimeline(
            id=_generate_id(),
            trip_id=trip.id,
            event_type="TRIP_REJECTED",
            actor_type=_coerce_actor_type(auth.role),
            actor_id=auth.actor_id,
            note=body.reason or "Trip rejected.",
            created_at_utc=now,
        )
    )
    await _create_outbox_event(session, trip, "trip.rejected.v1")
    await session.commit()

    trip = await _get_trip_or_404(session, trip.id)
    resource = trip_to_resource(trip)
    return _json_response(200, resource.model_dump(mode="json"), _response_headers_for_trip(trip))


@router.post("/api/v1/trips/{base_trip_id}/empty-return", response_model=TripResource, status_code=201)
async def create_empty_return(
    base_trip_id: str,
    body: EmptyReturnRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(user_auth_dependency),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> Any:
    """Create a reverse derived empty-return trip from a completed base trip."""
    auth = _require_admin(auth)
    current_version = require_trip_if_match(request, base_trip_id)
    request_body = body.model_dump(exclude_none=True)
    request_hash = _merged_payload_hash(request_body)
    endpoint_fp = f"empty_return:{auth.actor_id}:{base_trip_id}"
    replay = await _check_idempotency_key(session, idempotency_key, endpoint_fp, request_hash)
    if replay is not None:
        return replay

    base_trip = await _get_trip_or_404(session, base_trip_id)
    if current_version != base_trip.version:
        raise trip_version_mismatch()
    if normalize_trip_status(base_trip.status) != TripStatus.COMPLETED.value:
        raise invalid_base_for_empty_return("Base trip must be COMPLETED before an empty return can be created.")
    if base_trip.is_empty_return:
        raise invalid_base_for_empty_return("Base trip is itself an empty return.")
    if is_deleted_trip_status(base_trip.status) or normalize_trip_status(base_trip.status) == TripStatus.REJECTED.value:
        raise invalid_base_for_empty_return("Base trip is not active.")
    if base_trip.route_pair_id is None:
        raise invalid_base_for_empty_return("Base trip is missing route pair context.")

    await ensure_trip_references_valid(
        driver_id=body.driver_id,
        vehicle_id=body.vehicle_id,
        trailer_id=body.trailer_id,
    )
    context = await fetch_trip_context(base_trip.route_pair_id)
    trip_start_utc = local_datetime_to_utc(body.trip_start_local, body.trip_timezone)
    status, review_reason = await _classify_manual_status(auth, trip_start_utc)
    now = utc_now()
    trip_id = _generate_id()
    trip = TripTrip(
        id=trip_id,
        trip_no=f"{base_trip.trip_no}-B",
        source_type=SourceType.EMPTY_RETURN_ADMIN,
        review_reason_code=review_reason,
        base_trip_id=base_trip.id,
        source_payload_hash=request_hash,
        driver_id=body.driver_id,
        vehicle_id=body.vehicle_id,
        trailer_id=body.trailer_id,
        trip_datetime_utc=trip_start_utc,
        trip_timezone=body.trip_timezone,
        tare_weight_kg=body.tare_weight_kg,
        gross_weight_kg=body.gross_weight_kg,
        net_weight_kg=body.net_weight_kg,
        is_empty_return=True,
        status=status,
        version=1,
        created_by_actor_type=_coerce_actor_type(auth.role),
        created_by_actor_id=auth.actor_id,
        created_at_utc=now,
        updated_at_utc=now,
    )
    apply_trip_context(trip, context, reverse=True)
    await assert_no_trip_overlap(
        session,
        driver_id=trip.driver_id,
        vehicle_id=trip.vehicle_id,
        trailer_id=trip.trailer_id,
        trip_start_utc=trip.trip_datetime_utc,
        planned_end_utc=trip.planned_end_utc or trip.trip_datetime_utc,
    )
    session.add(trip)
    session.add(
        TripTripEvidence(
            id=_generate_id(),
            trip_id=trip_id,
            evidence_source=EvidenceSource.ADMIN_MANUAL,
            evidence_kind=EvidenceKind.MANUAL_ENTRY,
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
            actor_type=_coerce_actor_type(auth.role),
            actor_id=auth.actor_id,
            note=body.note or f"Empty return created from {base_trip.trip_no}.",
            payload_json=json.dumps({"base_trip_id": base_trip.id}),
            created_at_utc=now,
        )
    )
    await _create_outbox_event(session, trip, "trip.created.v1")
    TRIP_CREATED_TOTAL.labels(source_type=trip.source_type, **get_standard_labels()).inc()
    if trip.status == TripStatus.COMPLETED:
        await _create_outbox_event(session, trip, "trip.completed.v1")
        TRIP_COMPLETED_TOTAL.labels(**get_standard_labels()).inc()

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
        raise _map_integrity_error(exc, trip_no=trip.trip_no) from exc

    return _json_response(201, resource_dict, headers)


@router.post("/api/v1/trips/{trip_id}/cancel", response_model=TripResource)
async def cancel_trip(
    trip_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    auth: AuthContext = Depends(user_auth_dependency),
) -> Any:
    """Soft-delete a trip under the TASK-0033 contract."""
    auth = _require_admin(auth)
    current_version = require_trip_if_match(request, trip_id)
    trip = await _get_trip_or_404(session, trip_id)

    if is_deleted_trip_status(trip.status):
        if current_version != trip.version:
            raise trip_version_mismatch()
        resource = trip_to_resource(trip)
        return _json_response(200, resource.model_dump(mode="json"), _response_headers_for_trip(trip))

    if current_version != trip.version:
        raise trip_version_mismatch()

    now = utc_now()
    trip.status = TripStatus.SOFT_DELETED.value
    trip.soft_deleted_at_utc = now
    trip.soft_deleted_by_actor_id = auth.actor_id
    trip.version += 1
    trip.updated_at_utc = now
    session.add(
        TripTripTimeline(
            id=_generate_id(),
            trip_id=trip.id,
            event_type="TRIP_CANCELLED",
            actor_type=_coerce_actor_type(auth.role),
            actor_id=auth.actor_id,
            note="Trip soft deleted.",
            created_at_utc=now,
        )
    )
    await _create_outbox_event(session, trip, "trip.soft_deleted.v1")
    TRIP_CANCELLED_TOTAL.labels(**get_standard_labels()).inc()
    await session.commit()

    trip = await _get_trip_or_404(session, trip.id)
    resource = trip_to_resource(trip)
    return _json_response(200, resource.model_dump(mode="json"), _response_headers_for_trip(trip))


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
