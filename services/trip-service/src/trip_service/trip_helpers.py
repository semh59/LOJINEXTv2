"""Trip-domain helper functions shared across routers."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

from fastapi.responses import JSONResponse
from platform_auth import TokenClaims
from sqlalchemy import and_, func, select, text
from sqlalchemy.dialects.postgresql import INTERVAL
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError, IntegrityError, NoResultFound, OperationalError

if TYPE_CHECKING:
    from trip_service.auth import AuthContext
    from trip_service.schemas import EditTripRequest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from ulid import ULID

from trip_service.config import settings
from trip_service.database import async_session_factory
from trip_service.dependencies import LocationTripContext
from trip_service.enums import ActorType, ReviewReasonCode, SourceType, TripStatus
from trip_service.errors import (
    idempotency_in_flight,
    idempotency_payload_mismatch,
    trip_completion_requirements_missing,
    trip_driver_overlap,
    trip_not_found,
    trip_trailer_overlap,
    trip_validation_error,
    trip_vehicle_overlap,
)
from trip_service.models import (
    TripAuditLogModel,
    TripIdempotencyRecord,
    TripOutbox,
    TripTrip,
    TripTripDeleteAudit,
    TripTripEnrichment,
    TripTripEvidence,
)
from trip_service.observability import get_standard_labels  # noqa: F401
from trip_service.schemas import EnrichmentSummary, EvidenceSummary, TripResource
from trip_service.state_machine import TripStateMachine

_REFERENCE_EXCLUDED_STATUSES = (TripStatus.REJECTED.value, TripStatus.SOFT_DELETED.value, "CANCELLED")
_MANUAL_CREATE_WINDOW_MINUTES = 30

logger = logging.getLogger("trip_service.trip_helpers")


def latest_evidence(trip: TripTrip) -> TripTripEvidence | None:
    """Return the most recent piece of evidence for this trip without lazy-loading."""
    if "evidence" not in trip.__dict__ or not trip.evidence:
        return None
    return sorted(trip.evidence, key=lambda e: (e.created_at_utc, e.id), reverse=True)[0]


def normalize_trip_status(status: str | TripStatus) -> str:
    """Return the canonical string value for a trip status.

    Legacy DB rows may carry 'CANCELLED' from a prior schema; these are
    treated as SOFT_DELETED for all read/serialization purposes.
    """
    raw = status.value if isinstance(status, TripStatus) else str(status)
    if raw == "CANCELLED":
        return TripStatus.SOFT_DELETED.value
    return raw


def is_deleted_trip_status(status: str) -> bool:
    """Return whether the raw or normalized status represents a soft-deleted trip."""
    return normalize_trip_status(status) == TripStatus.SOFT_DELETED.value


def trip_to_resource(trip: TripTrip) -> TripResource:
    """Map ORM model to the public trip resource contract."""
    enrichment_summary = None
    if "enrichment" in trip.__dict__ and trip.enrichment:
        enrichment_summary = EnrichmentSummary(
            enrichment_status=trip.enrichment.enrichment_status,
            route_status=trip.enrichment.route_status,
            data_quality_flag=trip.enrichment.data_quality_flag,
        )

    evidence_summary = None
    evidence = latest_evidence(trip)
    if evidence is not None:
        evidence_summary = EvidenceSummary(
            normalized_truck_plate=evidence.normalized_truck_plate,
            normalized_trailer_plate=evidence.normalized_trailer_plate,
            origin_name_raw=evidence.origin_name_raw,
            destination_name_raw=evidence.destination_name_raw,
        )

    return TripResource(
        id=trip.id,
        trip_no=trip.trip_no,
        source_type=trip.source_type,
        source_slip_no=trip.source_slip_no,
        source_reference_key=trip.source_reference_key,
        review_reason_code=trip.review_reason_code,
        base_trip_id=trip.base_trip_id,
        driver_id=trip.driver_id or "",
        vehicle_id=trip.vehicle_id,
        trailer_id=trip.trailer_id,
        route_pair_id=trip.route_pair_id,
        route_id=trip.route_id,
        origin_location_id=trip.origin_location_id,
        origin_name_snapshot=trip.origin_name_snapshot,
        destination_location_id=trip.destination_location_id,
        destination_name_snapshot=trip.destination_name_snapshot,
        trip_datetime_utc=trip.trip_datetime_utc,
        trip_timezone=trip.trip_timezone,
        planned_duration_s=trip.planned_duration_s,
        planned_end_utc=trip.planned_end_utc,
        tare_weight_kg=trip.tare_weight_kg,
        gross_weight_kg=trip.gross_weight_kg,
        net_weight_kg=trip.net_weight_kg,
        is_empty_return=trip.is_empty_return,
        status=normalize_trip_status(trip.status),
        version=trip.version,
        enrichment=enrichment_summary,
        evidence_summary=evidence_summary,
        created_at_utc=trip.created_at_utc,
        updated_at_utc=trip.updated_at_utc,
        soft_deleted_at_utc=trip.soft_deleted_at_utc,
    )


def trip_complete_errors(trip: TripTrip) -> list[dict[str, str]]:
    """Return field-level completeness errors for approval/transition checks."""
    errors: list[dict[str, str]] = []
    required_fields: tuple[tuple[str, Any], ...] = (
        ("body.vehicle_id", trip.vehicle_id),
        ("body.route_pair_id", trip.route_pair_id),
        ("body.route_id", trip.route_id),
        ("body.origin_location_id", trip.origin_location_id),
        ("body.origin_name_snapshot", trip.origin_name_snapshot),
        ("body.destination_location_id", trip.destination_location_id),
        ("body.destination_name_snapshot", trip.destination_name_snapshot),
        ("body.tare_weight_kg", trip.tare_weight_kg),
        ("body.gross_weight_kg", trip.gross_weight_kg),
        ("body.net_weight_kg", trip.net_weight_kg),
        ("body.planned_duration_s", trip.planned_duration_s),
        ("body.planned_end_utc", trip.planned_end_utc),
    )
    for field_name, value in required_fields:
        if value is None:
            errors.append({"field": field_name, "message": "This field is required before the trip can be completed."})
    return errors


def trip_is_complete(trip: TripTrip) -> bool:
    """Return whether the trip has every field required for approval/completion."""
    return not trip_complete_errors(trip)


def validate_trip_transition(trip: TripTrip, next_status: TripStatus) -> None:
    """Validate that the trip can transition to the given status."""
    current_status = TripStatus(normalize_trip_status(trip.status))
    TripStateMachine(current_status).transition_to(next_status)


def _ensure_payload_size(payload: str, limit_kb: int = 512) -> str:
    """Ensure the payload string does not exceed a safety limit for DB storage."""
    if len(payload.encode("utf-8")) > limit_kb * 1024:
        raise trip_validation_error(f"Evidence payload exceeds {limit_kb}KB limit.")
    return payload


def transition_trip(trip: TripTrip, next_status: TripStatus) -> None:
    """Transition the trip to the next status using the state machine."""
    validate_trip_transition(trip, next_status)
    trip.status = next_status.value
    trip.version += 1
    trip.updated_at_utc = utc_now()


def calculate_planned_end(trip_start_utc: datetime, planned_duration_s: int) -> datetime:
    """Calculate the planned trip end timestamp from start + duration."""
    return trip_start_utc + timedelta(seconds=planned_duration_s)


def apply_trip_context(trip: TripTrip, context: LocationTripContext, *, reverse: bool) -> None:
    """Apply forward or reverse route-pair context to a trip."""
    trip.route_pair_id = context.pair_id
    trip.origin_location_id = context.destination_location_id if reverse else context.origin_location_id
    trip.origin_name_snapshot = context.destination_name if reverse else context.origin_name
    trip.destination_location_id = context.origin_location_id if reverse else context.destination_location_id
    trip.destination_name_snapshot = context.origin_name if reverse else context.destination_name
    trip.route_id = context.reverse_route_id if reverse else context.forward_route_id
    trip.planned_duration_s = context.reverse_duration_s if reverse else context.forward_duration_s
    trip.planned_end_utc = (
        calculate_planned_end(trip.trip_datetime_utc, trip.planned_duration_s)
        if trip.planned_duration_s is not None
        else None
    )


def _advisory_lock_key(resource_type: str, resource_id: str) -> int:
    """Derive a stable signed 64-bit advisory lock key for a trip resource."""
    digest = hashlib.sha256(f"{resource_type}:{resource_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


async def _acquire_overlap_locks(
    session: AsyncSession,
    *,
    driver_id: str | None,
    vehicle_id: str | None,
    trailer_id: str | None,
) -> None:
    """Lock trip resources in sorted order so concurrent writers serialize cleanly."""
    keys: set[int] = set()
    if driver_id is not None:
        keys.add(_advisory_lock_key("driver", driver_id))
    if vehicle_id is not None:
        keys.add(_advisory_lock_key("vehicle", vehicle_id))
    if trailer_id is not None:
        keys.add(_advisory_lock_key("trailer", trailer_id))

    for key in sorted(keys):
        await session.execute(select(func.pg_advisory_xact_lock(key)))


async def _find_overlap(
    session: AsyncSession,
    *,
    field_name: str,
    field_value: str,
    trip_start_utc: datetime,
    planned_end_utc: datetime,
    exclude_trip_id: str | None = None,
) -> TripTrip | None:
    """Return the first overlapping trip for the given resource window."""
    column = getattr(TripTrip, field_name)
    conditions = [
        column == field_value,
        TripTrip.status.not_in(_REFERENCE_EXCLUDED_STATUSES),
        TripTrip.trip_datetime_utc < planned_end_utc,
        func.coalesce(
            TripTrip.planned_end_utc,
            TripTrip.trip_datetime_utc + func.cast(text("'24 hours'"), INTERVAL),
        )
        > trip_start_utc,
    ]
    if exclude_trip_id is not None:
        conditions.append(TripTrip.id != exclude_trip_id)

    result = await session.execute(select(TripTrip).where(and_(*conditions)).limit(1))
    return result.scalar_one_or_none()


async def assert_no_trip_overlap(
    session: AsyncSession,
    *,
    driver_id: str | None,
    vehicle_id: str | None,
    trailer_id: str | None,
    trip_start_utc: datetime,
    planned_end_utc: datetime,
    exclude_trip_id: str | None = None,
) -> None:
    """Raise a stable 409 error when driver, vehicle, or trailer windows overlap."""
    await _acquire_overlap_locks(
        session,
        driver_id=driver_id,
        vehicle_id=vehicle_id,
        trailer_id=trailer_id,
    )

    driver_overlap = await _find_overlap(
        session,
        field_name="driver_id",
        field_value=cast(str, driver_id),
        trip_start_utc=trip_start_utc,
        planned_end_utc=planned_end_utc,
        exclude_trip_id=exclude_trip_id,
    )
    if driver_overlap is not None:
        raise trip_driver_overlap(
            f"Driver {driver_id} already overlaps trip {driver_overlap.trip_no} between planned windows."
        )

    if vehicle_id is not None:
        vehicle_overlap = await _find_overlap(
            session,
            field_name="vehicle_id",
            field_value=vehicle_id,
            trip_start_utc=trip_start_utc,
            planned_end_utc=planned_end_utc,
            exclude_trip_id=exclude_trip_id,
        )
        if vehicle_overlap is not None:
            raise trip_vehicle_overlap(
                f"Vehicle {vehicle_id} already overlaps trip {vehicle_overlap.trip_no} between planned windows."
            )

    if trailer_id is not None:
        trailer_overlap = await _find_overlap(
            session,
            field_name="trailer_id",
            field_value=trailer_id,
            trip_start_utc=trip_start_utc,
            planned_end_utc=planned_end_utc,
            exclude_trip_id=exclude_trip_id,
        )
        if trailer_overlap is not None:
            raise trip_trailer_overlap(
                f"Trailer {trailer_id} already overlaps trip {trailer_overlap.trip_no} between planned windows."
            )


def serialize_trip_admin(trip: TripTrip) -> dict[str, Any]:
    """Serialize a full trip aggregate for high-fidelity audit snapshots."""
    return serialize_trip_snapshot(trip)


async def _write_audit(
    session: AsyncSession,
    *,
    trip_id: str,
    action_type: str,
    actor_id: str,
    actor_role: str,
    old_snapshot: dict[str, Any] | None = None,
    new_snapshot: dict[str, Any] | None = None,
    changed_fields: list[str] | None = None,
    reason: str | None = None,
    request_id: str | None = None,
) -> None:
    """Write a high-fidelity audit log entry for a trip mutation."""
    session.add(
        TripAuditLogModel(
            audit_id=str(ULID()),
            trip_id=trip_id,
            action_type=action_type,
            old_snapshot_json=json.dumps(old_snapshot, default=str) if old_snapshot else None,
            new_snapshot_json=json.dumps(new_snapshot, default=str) if new_snapshot else None,
            changed_fields_json=json.dumps(changed_fields) if changed_fields else None,
            actor_id=actor_id,
            actor_role=actor_role,
            reason=reason,
            request_id=request_id,
            created_at_utc=utc_now(),
        )
    )


def _build_outbox_row(*, trip_id: str, aggregate_version: int, event_name: str, payload: dict[str, Any]) -> TripOutbox:
    """Create an in-memory outbox row ready to be added to the current transaction."""
    now = utc_now()
    return TripOutbox(
        event_id=str(ULID()),
        aggregate_type="TRIP",
        aggregate_id=trip_id,
        aggregate_version=aggregate_version,
        event_name=event_name,
        schema_version=1,
        payload_json=json.dumps(payload, default=str),
        partition_key=trip_id,
        publish_status="PENDING",
        attempt_count=0,
        next_attempt_at_utc=now,
        last_error_code=None,
        claim_token=None,
        claim_expires_at_utc=None,
        claimed_by_worker=None,
        created_at_utc=now,
        published_at_utc=None,
    )


async def _create_outbox_event(
    session: AsyncSession,
    trip: TripTrip,
    event_name: str,
    payload: dict[str, Any] | None = None,
) -> TripOutbox:
    """Add an outbox row to the current session for the given trip aggregate."""
    row = _build_outbox_row(
        trip_id=trip.id,
        aggregate_version=trip.version,
        event_name=event_name,
        payload=payload or _event_payload(trip),
    )
    session.add(row)
    return row


async def _write_outbox(
    session: AsyncSession,
    *,
    trip_id: str,
    event_name: str,
    payload: dict[str, Any],
) -> TripOutbox:
    """Add a generic outbox event to the current transaction."""
    row = _build_outbox_row(
        trip_id=trip_id,
        aggregate_version=int(payload.get("version", 1)),
        event_name=event_name,
        payload=payload,
    )
    session.add(row)
    return row


def serialize_trip_snapshot(trip: TripTrip) -> dict[str, Any]:
    """Serialize a full trip aggregate snapshot for immutable delete audit rows."""
    return {
        "trip": trip_to_resource(trip).model_dump(mode="json"),
        "enrichment": (
            {
                "enrichment_status": trip.enrichment.enrichment_status,
                "route_status": trip.enrichment.route_status,
                "data_quality_flag": trip.enrichment.data_quality_flag,
                "enrichment_attempt_count": trip.enrichment.enrichment_attempt_count,
                "last_enrichment_error_code": trip.enrichment.last_enrichment_error_code,
            }
            if trip.enrichment
            else None
        ),
        "evidence": [
            {
                "id": evidence.id,
                "evidence_source": evidence.evidence_source,
                "evidence_kind": evidence.evidence_kind,
                "source_slip_no": evidence.source_slip_no,
                "telegram_message_id": evidence.telegram_message_id,
                "file_key": evidence.file_key,
                "row_number": evidence.row_number,
                "raw_text_ref": evidence.raw_text_ref,
                "ocr_confidence": evidence.ocr_confidence,
                "normalized_truck_plate": evidence.normalized_truck_plate,
                "normalized_trailer_plate": evidence.normalized_trailer_plate,
                "origin_name_raw": evidence.origin_name_raw,
                "destination_name_raw": evidence.destination_name_raw,
                "raw_payload_json": evidence.raw_payload_json,
                "created_at_utc": evidence.created_at_utc.isoformat(),
            }
            for evidence in sorted(trip.evidence, key=lambda row: row.created_at_utc)
        ],
        "timeline": [
            {
                "id": event.id,
                "event_type": event.event_type,
                "actor_type": event.actor_type,
                "actor_id": event.actor_id,
                "note": event.note,
                "payload_json": json.loads(event.payload_json) if event.payload_json else None,
                "created_at_utc": event.created_at_utc.isoformat(),
            }
            for event in sorted(trip.timeline, key=lambda row: row.created_at_utc)
        ],
    }


def build_delete_audit(
    *,
    audit_id: str,
    trip: TripTrip,
    actor_id: str,
    actor_role: str,
    reason: str,
    deleted_at_utc: datetime,
) -> TripTripDeleteAudit:
    """Build the immutable hard-delete audit row for a trip aggregate."""
    return TripTripDeleteAudit(
        audit_id=audit_id,
        trip_id=trip.id,
        trip_no=trip.trip_no,
        actor_id=actor_id,
        actor_role=actor_role,
        reason=reason,
        snapshot_json=serialize_trip_snapshot(trip),
        deleted_at_utc=deleted_at_utc,
        created_at_utc=deleted_at_utc,
    )


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


async def _check_idempotency_key(
    session: AsyncSession,
    idempotency_key: str | None,
    endpoint_fingerprint: str,
    request_hash: str,
) -> JSONResponse | None:
    """Replay a stored idempotent response when the same key is reused.

    Refactored to avoid recursion and premature session commits.
    """
    if not idempotency_key:
        return None

    now = utc_now()
    async with async_session_factory() as secondary_session:
        claim_stmt = (
            pg_insert(TripIdempotencyRecord)
            .values(
                idempotency_key=idempotency_key,
                endpoint_fingerprint=endpoint_fingerprint,
                request_hash=request_hash,
                response_status=0,
                response_headers_json={},
                response_body_json="{}",
                created_at_utc=now,
                expires_at_utc=now + timedelta(hours=settings.idempotency_retention_hours),
            )
            .on_conflict_do_nothing(index_elements=["idempotency_key", "endpoint_fingerprint"])
        )
        claim_result = await secondary_session.execute(claim_stmt)
        await secondary_session.commit()

        if getattr(claim_result, "rowcount", 0) == 1:
            return None

    try:
        record = (
            await session.execute(
                select(TripIdempotencyRecord)
                .where(
                    TripIdempotencyRecord.idempotency_key == idempotency_key,
                    TripIdempotencyRecord.endpoint_fingerprint == endpoint_fingerprint,
                )
                .with_for_update(nowait=True)
            )
        ).scalar_one()
    except (NoResultFound, IntegrityError, OperationalError, DBAPIError):
        raise idempotency_in_flight()

    if record.request_hash != request_hash:
        raise idempotency_payload_mismatch()

    if record.response_status == 0:
        # If the placeholder is stale (> 60s), notify client to retry.
        # We cleanup the stale record in a separate session.
        if (utc_now() - record.created_at_utc).total_seconds() > 60:
            logger.warning(
                "Idempotency %s: Stale in-flight record detected (created at %s)",
                idempotency_key,
                record.created_at_utc,
            )
            async with async_session_factory() as cleanup_session:
                await cleanup_session.execute(
                    text(
                        "DELETE FROM trip_idempotency_records WHERE idempotency_key = :k AND endpoint_fingerprint = :f"
                    ),
                    {"k": idempotency_key, "f": endpoint_fingerprint},
                )
                await cleanup_session.commit()

        raise idempotency_in_flight()

    content = record.response_body_json
    if isinstance(content, (str, bytes)):
        content = json.loads(content)
    response = JSONResponse(status_code=record.response_status, content=content)
    for key, value in record.response_headers_json.items():
        response.headers[key] = value
    return response


def get_actor_actor_role(claims: TokenClaims) -> tuple[str, str]:
    """Extract actor ID and role from token claims."""
    return str(claims.sub), str(claims.role)


async def _get_trip_or_404(session: AsyncSession, trip_id: str) -> TripTrip:
    """Fetch a trip by ID or raise a 404 NOT FOUND error."""
    stmt = (
        select(TripTrip)
        .where(TripTrip.id == trip_id)
        .options(
            selectinload(TripTrip.enrichment),
            selectinload(TripTrip.evidence),
            selectinload(TripTrip.timeline),
            selectinload(TripTrip.empty_return_children),
        )
    )
    trip = (await session.execute(stmt)).unique().scalar_one_or_none()
    if trip is None:
        raise trip_not_found(f"Trip {trip_id} not found.")
    return trip


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
    from trip_service.errors import (
        empty_return_already_exists,
        internal_error,
        source_slip_conflict,
        trip_no_conflict,
        trip_source_reference_conflict,
    )

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


def _event_payload(trip: TripTrip) -> dict[str, Any]:
    """Generate a standard event payload for a trip.

    Includes all fields downstream consumers need to avoid a fan-out GET /trips/{id}.
    """
    return {
        "trip_id": trip.id,
        "trip_no": trip.trip_no,
        "status": normalize_trip_status(trip.status),
        "version": trip.version,
        "driver_id": trip.driver_id,
        "vehicle_id": trip.vehicle_id,
        "trailer_id": trip.trailer_id,
        "route_id": trip.route_id,
        "route_pair_id": trip.route_pair_id,
        "origin_location_id": trip.origin_location_id,
        "destination_location_id": trip.destination_location_id,
        "trip_datetime_utc": trip.trip_datetime_utc.isoformat() if trip.trip_datetime_utc else None,
        "planned_end_utc": trip.planned_end_utc.isoformat() if trip.planned_end_utc else None,
        "source_type": trip.source_type,
        "updated_at_utc": trip.updated_at_utc.isoformat() if trip.updated_at_utc else utc_now().isoformat(),
    }


def _validate_trip_weights(tare_weight_kg: int | None, gross_weight_kg: int | None, net_weight_kg: int | None) -> None:
    """Validate weight invariants before hitting database constraints."""
    from trip_service.errors import trip_validation_error

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
    from trip_service.enums import DataQualityFlag

    if source_type in (SourceType.ADMIN_MANUAL, SourceType.EMPTY_RETURN_ADMIN, SourceType.EXCEL_IMPORT):
        return DataQualityFlag.HIGH
    if ocr_confidence is not None and ocr_confidence >= 0.90 and route_resolved:
        return DataQualityFlag.HIGH
    if ocr_confidence is not None and ocr_confidence >= 0.70:
        return DataQualityFlag.MEDIUM
    if not route_resolved:
        return DataQualityFlag.MEDIUM
    return DataQualityFlag.LOW


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
            from trip_service.errors import trip_change_reason_required

            raise trip_change_reason_required("SUPER_ADMIN must provide change_reason to reassign imported driver.")
        return
    from trip_service.errors import trip_source_locked_field

    raise trip_source_locked_field("ADMIN cannot change driver_id on imported trips.")


async def _classify_manual_status(auth: AuthContext, trip_datetime_utc: datetime) -> tuple[TripStatus, str | None]:
    """Determine initial status and review reason for a manually created trip."""
    now = datetime.now(UTC)
    if auth.role == ActorType.SUPER_ADMIN.value:
        if trip_datetime_utc > now:
            return TripStatus.PENDING_REVIEW, ReviewReasonCode.FUTURE_MANUAL
        return TripStatus.COMPLETED, None

    grace_start = now - timedelta(minutes=_MANUAL_CREATE_WINDOW_MINUTES)
    if trip_datetime_utc < grace_start or trip_datetime_utc > now:
        from trip_service.errors import trip_invalid_date_window

        raise trip_invalid_date_window(
            "ADMIN may only create manual trips in the last 30 minutes and may not create future trips."
        )
    return TripStatus.COMPLETED, None


def _ensure_complete_for_completion(trip: TripTrip) -> None:
    """Raise a contract error if the trip is not complete enough for a final transition."""
    if trip_is_complete(trip):
        return
    missing = ", ".join(error["field"] for error in trip_complete_errors(trip))
    raise trip_completion_requirements_missing(f"Trip is missing required fields: {missing}.")


def _set_enrichment_state(
    trip: TripTrip,
    enrichment: TripTripEnrichment,
    *,
    source_type: str,
    route_ready: bool,
    ocr_confidence: float | None = None,
) -> None:
    """Synchronize enrichment fields with the current trip payload completeness."""
    from trip_service.enums import EnrichmentStatus, RouteStatus

    enrichment.route_status = RouteStatus.READY if route_ready else RouteStatus.PENDING
    enrichment.enrichment_status = EnrichmentStatus.READY if route_ready else EnrichmentStatus.PENDING
    enrichment.data_quality_flag = _compute_data_quality_flag(source_type, ocr_confidence, route_resolved=route_ready)
    enrichment.claim_token = None
    enrichment.claim_expires_at_utc = None
    enrichment.claimed_by_worker = None
    enrichment.last_enrichment_error_code = None
    enrichment.next_retry_at_utc = None
    enrichment.updated_at_utc = utc_now()


def _merged_payload_hash(payload: dict[str, Any]) -> str:
    """Generate a stable hash for a request payload."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _generate_id() -> str:
    """Generate a ULID string for primary keys."""
    return str(ULID())


def _coerce_actor_type(role: str) -> str:
    """Normalize role strings for persistence/audit fields."""
    return str(role)


def _resolve_idempotency_key(canonical_key: str | None, legacy_key: str | None) -> str | None:
    """Prefer the canonical idempotency header while still accepting the legacy alias."""
    return canonical_key or legacy_key


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
    """Persist idempotency replay material for later requests.

    Note: We use a secondary session to ensure the result is committed
    even if the main transaction has already finished or if we want
    to ensure atomic persistence of the replay data.
    """
    now = utc_now()
    async with async_session_factory() as secondary_session:
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
        await secondary_session.execute(stmt)
        await secondary_session.commit()
