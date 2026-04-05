"""Trip-domain helper functions shared across routers."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from platform_auth import TokenClaims


from trip_service.dependencies import LocationTripContext
from trip_service.enums import TripStatus
from trip_service.errors import (
    trip_driver_overlap,
    trip_not_found,
    trip_trailer_overlap,
    trip_vehicle_overlap,
)
from trip_service.models import (
    TripIdempotencyRecord,
    TripTrip,
    TripTripDeleteAudit,
    TripTripEvidence,
)
from trip_service.schemas import EnrichmentSummary, EvidenceSummary, TripResource
from trip_service.state_machine import TripStateMachine


def latest_evidence(trip: TripTrip) -> TripTripEvidence | None:
    """Return the most recent piece of evidence for this trip without lazy-loading."""
    if "evidence" not in trip.__dict__ or not trip.evidence:
        return None
    return sorted(trip.evidence, key=lambda e: e.created_at_utc, reverse=True)[0]


def trip_to_resource(trip: TripTrip) -> TripResource:
    """Map ORM model to the public trip resource contract."""
    # Avoid lazy-loading if not already present
    enrichment_summary = None
    if "enrichment" in trip.__dict__ and trip.enrichment:
        enrichment_summary = EnrichmentSummary(
            enrichment_status=trip.enrichment.enrichment_status,
            route_status=trip.enrichment.route_status,
            data_quality_flag=trip.enrichment.data_quality_flag,
        )

    evidence_summary = None
    ev = latest_evidence(trip)
    if ev is not None:
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
        source_reference_key=trip.source_reference_key,
        review_reason_code=trip.review_reason_code,
        base_trip_id=trip.base_trip_id,
        driver_id=trip.driver_id,
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
        status=trip.status,
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
    """
    Validate that the trip can transition to the given status.
    Raises ValueError if invalid.
    """
    sm = TripStateMachine(trip.status)
    sm.transition_to(next_status)


def transition_trip(trip: TripTrip, next_status: TripStatus) -> None:
    """
    Transition the trip to the next status using the state machine.
    Updates the model status and version.
    """
    validate_trip_transition(trip, next_status)
    trip.status = next_status
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
    driver_id: str,
    vehicle_id: str | None,
    trailer_id: str | None,
) -> None:
    """Lock trip resources in sorted order so concurrent writers serialize cleanly."""
    keys = {_advisory_lock_key("driver", driver_id)}
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
        TripTrip.status.not_in((TripStatus.CANCELLED, TripStatus.REJECTED)),
        TripTrip.planned_end_utc.is_not(None),
        TripTrip.trip_datetime_utc < planned_end_utc,
        TripTrip.planned_end_utc > trip_start_utc,
    ]
    if exclude_trip_id is not None:
        conditions.append(TripTrip.id != exclude_trip_id)

    result = await session.execute(select(TripTrip).where(and_(*conditions)).limit(1))
    return result.scalar_one_or_none()


async def assert_no_trip_overlap(
    session: AsyncSession,
    *,
    driver_id: str,
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
        field_value=driver_id,
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
    from trip_service.models import TripAuditLogModel  # Avoid circular import

    audit_id = str(ULID())
    session.add(
        TripAuditLogModel(
            audit_id=audit_id,
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


def _write_outbox(
    *,
    trip_id: str,
    event_name: str,
    payload: dict[str, Any],
) -> Any:
    """Create an outbox event for reliable delivery via the outbox relay."""
    from trip_service.models import TripOutbox  # Avoid circular import

    return TripOutbox(
        event_id=str(ULID()),
        aggregate_type="TRIP",
        aggregate_id=trip_id,
        aggregate_version=payload.get("version", 1),
        event_name=event_name,
        schema_version=1,
        payload_json=json.dumps(payload, default=str),
        partition_key=trip_id,
        publish_status="PENDING",
        attempt_count=0,
        next_attempt_at_utc=utc_now(),
        last_error_code=None,
        claim_token=None,
        claim_expires_at_utc=None,
        claimed_by_worker=None,
        created_at_utc=utc_now(),
    )


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
) -> dict[str, Any] | None:
    """Check if an idempotency key has already been used for this endpoint."""
    if not idempotency_key:
        return None

    stmt = select(TripIdempotencyRecord).where(
        and_(
            TripIdempotencyRecord.idempotency_key == idempotency_key,
            TripIdempotencyRecord.endpoint_fingerprint == endpoint_fingerprint,
        )
    )
    result = await session.execute(stmt)
    record = result.scalar_one_or_none()

    if record:
        # Simple hash check to ensure payload hasn't changed for the same key
        if record.request_hash != request_hash:
            raise ValueError("Idempotency key already used with a different request payload.")
        return json.loads(record.response_body_json)
    return None


async def _save_idempotency_response(
    session: AsyncSession,
    *,
    idempotency_key: str,
    endpoint_fingerprint: str,
    request_payload: dict[str, Any],
    response_body: dict[str, Any],
    status_code: int,
) -> None:
    """Persist the response for an idempotency key."""
    payload_hash = hashlib.sha256(json.dumps(request_payload, sort_keys=True).encode()).hexdigest()
    session.add(
        TripIdempotencyRecord(
            idempotency_key=idempotency_key,
            endpoint_fingerprint=endpoint_fingerprint,
            request_hash=payload_hash,
            response_status=status_code,
            response_body_json=json.dumps(response_body),
            created_at_utc=utc_now(),
            expires_at_utc=utc_now() + timedelta(hours=24),
        )
    )


def get_actor_actor_role(claims: TokenClaims) -> tuple[str, str]:
    """Extract actor ID and role from token claims."""
    return str(claims.sub), str(claims.role)


async def _get_trip_or_404(session: AsyncSession, trip_id: str) -> TripTrip:
    """Fetch a trip by ID or raise a 404 NOT FOUND error."""
    stmt = (
        select(TripTrip)
        .where(TripTrip.id == trip_id)
        .outerjoin(TripTrip.enrichment)
        .outerjoin(TripTrip.evidence)
        .outerjoin(TripTrip.timeline)
    )
    result = await session.execute(stmt)
    trip = result.unique().scalar_one_or_none()
    if not trip:
        raise trip_not_found(f"Trip {trip_id} not found.")
    return trip


def _event_payload(trip: TripTrip) -> dict[str, Any]:
    """Generate a standard event payload for a trip."""
    return {
        "trip_id": trip.id,
        "trip_no": trip.trip_no,
        "status": trip.status,
        "version": trip.version,
        "updated_at_utc": (
            trip.updated_at_utc.isoformat()
            if hasattr(trip, "updated_at_utc") and trip.updated_at_utc
            else utc_now().isoformat()
        ),
    }


async def _classify_manual_status(auth: Any, trip_datetime_utc: datetime) -> tuple[TripStatus, str | None]:
    """Determine initial status and review reason for a manually created trip."""
    try:
        from trip_service.enums import ActorType, ReviewReasonCode

        if auth.role in {ActorType.MANAGER.value, ActorType.SUPER_ADMIN.value}:
            return TripStatus.ASSIGNED, None
        return TripStatus.PENDING_REVIEW, ReviewReasonCode.MANUAL_ENTRY
    except Exception as e:
        import traceback

        print(f"DEBUG_STACKTRACER: {traceback.format_exc()}")
        raise e


def _ensure_complete_for_completion(trip: TripTrip) -> None:
    """Raise ValueError if the trip is not complete enough for a final transition."""
    errors = trip_complete_errors(trip)
    if errors:
        raise ValueError(f"Trip is incomplete: {errors}")


def _merged_payload_hash(payload: dict[str, Any]) -> str:
    """Generate a stable hash for a request payload."""
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
