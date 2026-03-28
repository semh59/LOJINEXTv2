"""Trip-domain helper functions shared across routers."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from trip_service.dependencies import LocationTripContext
from trip_service.enums import TripStatus
from trip_service.errors import trip_driver_overlap, trip_trailer_overlap, trip_vehicle_overlap
from trip_service.models import TripTrip, TripTripDeleteAudit, TripTripEvidence
from trip_service.schemas import EnrichmentSummary, EvidenceSummary, TripResource


def latest_evidence(trip: TripTrip) -> TripTripEvidence | None:
    """Return the most recent evidence row without relying on relationship order."""
    if not trip.evidence:
        return None
    return max(trip.evidence, key=lambda evidence: evidence.created_at_utc)


def trip_to_resource(trip: TripTrip) -> TripResource:
    """Map ORM model to the public trip resource contract."""
    enrichment_summary = None
    if trip.enrichment:
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
        TripTrip.status.not_in((TripStatus.SOFT_DELETED, TripStatus.REJECTED)),
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
