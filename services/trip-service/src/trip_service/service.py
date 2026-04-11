"""Business logic layer for Trip Service."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from trip_service.auth import AuthContext
from trip_service.dependencies import (
    ensure_trip_references_valid,
    fetch_trip_context,
)
from trip_service.enums import (
    DataQualityFlag,
    EnrichmentStatus,
    EvidenceKind,
    EvidenceSource,
    RouteStatus,
    SourceType,
    TripStatus,
)
from trip_service.errors import (
    invalid_base_for_empty_return,
    invalid_status_transition,
    route_required_for_completion,
    trip_if_match_required,
    trip_version_mismatch,
)
from trip_service.middleware import make_etag, parse_etag_version
from trip_service.models import (
    TripTrip,
    TripTripEnrichment,
    TripTripEvidence,
    TripTripTimeline,
)
from trip_service.observability import (
    TRIP_CANCELLED_TOTAL,
    TRIP_COMPLETED_TOTAL,
    TRIP_CREATED_TOTAL,
    get_standard_labels,
)
from trip_service.schemas import (
    ApproveRequest,
    EditTripRequest,
    EmptyReturnRequest,
    ManualCreateRequest,
    RejectRequest,
)
from trip_service.timezones import local_datetime_to_utc
from trip_service.trip_helpers import (
    _check_idempotency_key,
    _classify_manual_status,
    _coerce_actor_type,
    _create_outbox_event,
    _ensure_complete_for_completion,
    _ensure_payload_size,
    _generate_id,
    _get_trip_or_404,
    _map_integrity_error,
    _maybe_require_change_reason,
    _merged_payload_hash,
    _resolve_idempotency_key,
    _save_idempotency_record,
    _set_enrichment_state,
    _validate_trip_weights,
    _write_audit,
    apply_trip_context,
    assert_no_trip_overlap,
    is_deleted_trip_status,
    normalize_trip_status,
    serialize_trip_admin,
    transition_trip,
    trip_to_resource,
)

logger = logging.getLogger("trip_service.service")


class TripService:
    """Coordinates business logic and database persistence for Trip operations."""

    def __init__(self, session: AsyncSession, auth: AuthContext):
        self.session = session
        self.auth = auth

    def _response_headers(self, trip: TripTrip) -> dict[str, str]:
        """Generate common response headers for a trip resource."""
        return {
            "ETag": make_etag(trip.id, trip.version),
            "X-Trip-Status": normalize_trip_status(trip.status),
        }

    def _normalize_replay_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """Ensure standard TitleCase for key headers to prevent KeyError in consumers."""
        normalized = {}
        title_map = {"etag": "ETag", "x-trip-status": "X-Trip-Status"}
        for k, v in headers.items():
            normalized[title_map.get(k.lower(), k)] = v
        return normalized

    async def create_trip(
        self,
        body: ManualCreateRequest,
        idempotency_key: str | None = None,
        legacy_idempotency_key: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Create a manual trip with overlap checks and idempotency."""
        effective_key = _resolve_idempotency_key(idempotency_key, legacy_idempotency_key)
        request_body = body.model_dump(exclude_none=True)
        request_hash = _merged_payload_hash(request_body)
        endpoint_fp = f"create_trip:{self.auth.actor_id}"

        replay = await _check_idempotency_key(self.session, effective_key, endpoint_fp, request_hash)
        if replay is not None:
            # Replay returns a JSONResponse — extract content and headers safely
            raw_body = replay.body
            if isinstance(raw_body, bytes):
                body_content = json.loads(raw_body)
            elif isinstance(raw_body, str):
                body_content = json.loads(raw_body)
            else:
                body_content = json.loads(str(raw_body))
            return body_content, self._normalize_replay_headers(dict(replay.headers))

        await ensure_trip_references_valid(
            driver_id=body.driver_id,
            vehicle_id=body.vehicle_id,
            trailer_id=body.trailer_id,
        )
        context = await fetch_trip_context(body.route_pair_id)
        trip_start_utc = local_datetime_to_utc(body.trip_start_local, body.trip_timezone)

        status, review_reason = await _classify_manual_status(self.auth, trip_start_utc)
        now = datetime.now(UTC)
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
            created_by_actor_type=_coerce_actor_type(self.auth.role),
            created_by_actor_id=self.auth.actor_id,
            created_at_utc=now,
            updated_at_utc=now,
        )
        apply_trip_context(trip, context, reverse=False)
        await assert_no_trip_overlap(
            self.session,
            driver_id=trip.driver_id,
            vehicle_id=trip.vehicle_id,
            trailer_id=trip.trailer_id,
            trip_start_utc=trip.trip_datetime_utc,
            planned_end_utc=trip.planned_end_utc
            if trip.planned_end_utc is not None
            else (trip.trip_datetime_utc + timedelta(hours=24)),
        )
        self.session.add(trip)
        self.session.add(
            TripTripEvidence(
                id=_generate_id(),
                trip_id=trip_id,
                evidence_source=EvidenceSource.ADMIN_MANUAL,
                evidence_kind=EvidenceKind.MANUAL_ENTRY,
                raw_payload_json=_ensure_payload_size(json.dumps(request_body, default=str)),
                created_at_utc=now,
            )
        )
        self.session.add(
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
        self.session.add(
            TripTripTimeline(
                id=_generate_id(),
                trip_id=trip_id,
                event_type="TRIP_CREATED",
                actor_type=_coerce_actor_type(self.auth.role),
                actor_id=self.auth.actor_id,
                note=body.note or "Manual trip created.",
                payload_json=json.dumps({"route_pair_id": body.route_pair_id}),
                created_at_utc=now,
            )
        )
        await _create_outbox_event(self.session, trip, "trip.created.v1")
        TRIP_CREATED_TOTAL.labels(source_type=trip.source_type, **get_standard_labels()).inc()

        if trip.status == TripStatus.COMPLETED:
            await _create_outbox_event(self.session, trip, "trip.completed.v1")
            TRIP_COMPLETED_TOTAL.labels(**get_standard_labels()).inc()

        try:
            await self.session.commit()
        except IntegrityError as exc:
            raise _map_integrity_error(exc, trip_no=trip.trip_no) from exc

        resource = trip_to_resource(trip)
        resource_dict = resource.model_dump(mode="json")
        headers = self._response_headers(trip)

        if effective_key:
            await _save_idempotency_record(
                self.session,
                idempotency_key=effective_key,
                endpoint_fingerprint=endpoint_fp,
                request_hash=request_hash,
                response_status=201,
                response_body=resource_dict,
                response_headers=headers,
            )

        return resource_dict, headers

    async def cancel_trip(self, trip_id: str, if_match: str | None = None) -> tuple[dict[str, Any], dict[str, str]]:
        """Soft-delete a trip."""
        trip = await _get_trip_or_404(self.session, trip_id)
        if not if_match:
            raise trip_if_match_required()
        parsed_version = parse_etag_version(if_match)
        if parsed_version is None or parsed_version != trip.version:
            raise trip_version_mismatch()

        if is_deleted_trip_status(trip.status):
            return trip_to_resource(trip).model_dump(mode="json"), self._response_headers(trip)

        now = datetime.now(UTC)
        old_snapshot = serialize_trip_admin(trip)
        transition_trip(trip, TripStatus.SOFT_DELETED)
        trip.soft_deleted_at_utc = now
        trip.soft_deleted_by_actor_id = self.auth.actor_id
        self.session.add(
            TripTripTimeline(
                id=_generate_id(),
                trip_id=trip.id,
                event_type="TRIP_CANCELLED",
                actor_type=_coerce_actor_type(self.auth.role),
                actor_id=self.auth.actor_id,
                note="Trip soft deleted.",
                created_at_utc=now,
            )
        )
        await _create_outbox_event(self.session, trip, "trip.soft_deleted.v1")
        TRIP_CANCELLED_TOTAL.labels(**get_standard_labels()).inc()

        await _write_audit(
            self.session,
            trip_id=trip.id,
            action_type="SOFT_DELETE",
            actor_id=self.auth.actor_id,
            actor_role=str(self.auth.role),
            old_snapshot=old_snapshot,
            new_snapshot=serialize_trip_admin(trip),
            reason="Trip soft deleted.",
        )

        await self.session.commit()
        return trip_to_resource(trip).model_dump(mode="json"), self._response_headers(trip)

    async def approve_trip(
        self, trip_id: str, body: ApproveRequest, if_match: str | None = None
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Approve a pending-review trip."""
        trip = await _get_trip_or_404(self.session, trip_id)
        if not if_match:
            raise trip_if_match_required()
        parsed_version = parse_etag_version(if_match)
        if parsed_version is None or parsed_version != trip.version:
            raise trip_version_mismatch()

        if normalize_trip_status(trip.status) != TripStatus.PENDING_REVIEW.value:
            raise invalid_status_transition("Only PENDING_REVIEW trips can be approved.")

        _ensure_complete_for_completion(trip)
        if trip.route_id is None or trip.planned_end_utc is None:
            raise route_required_for_completion()

        await assert_no_trip_overlap(
            self.session,
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

        now = datetime.now(UTC)
        self.session.add(
            TripTripTimeline(
                id=_generate_id(),
                trip_id=trip.id,
                event_type="TRIP_APPROVED",
                actor_type=_coerce_actor_type(self.auth.role),
                actor_id=self.auth.actor_id,
                note=body.note or "Trip approved.",
                created_at_utc=now,
            )
        )
        await _create_outbox_event(self.session, trip, "trip.completed.v1")
        TRIP_COMPLETED_TOTAL.labels(**get_standard_labels()).inc()

        try:
            await self.session.commit()
        except IntegrityError as exc:
            raise _map_integrity_error(exc, trip_no=trip.trip_no) from exc

        return trip_to_resource(trip).model_dump(mode="json"), self._response_headers(trip)

    async def reject_trip(
        self, trip_id: str, body: RejectRequest, if_match: str | None = None
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Reject a pending-review trip."""
        trip = await _get_trip_or_404(self.session, trip_id)
        if not if_match:
            raise trip_if_match_required()
        parsed_version = parse_etag_version(if_match)
        if parsed_version is None or parsed_version != trip.version:
            raise trip_version_mismatch()

        if normalize_trip_status(trip.status) != TripStatus.PENDING_REVIEW.value:
            raise invalid_status_transition("Only PENDING_REVIEW trips can be rejected.")

        now = datetime.now(UTC)
        old_snapshot = serialize_trip_admin(trip)
        transition_trip(trip, TripStatus.REJECTED)
        self.session.add(
            TripTripTimeline(
                id=_generate_id(),
                trip_id=trip.id,
                event_type="TRIP_REJECTED",
                actor_type=_coerce_actor_type(self.auth.role),
                actor_id=self.auth.actor_id,
                note=body.reason or "Trip rejected.",
                created_at_utc=now,
            )
        )
        await _create_outbox_event(self.session, trip, "trip.rejected.v1")

        await _write_audit(
            self.session,
            trip_id=trip.id,
            action_type="REJECT",
            actor_id=self.auth.actor_id,
            actor_role=str(self.auth.role),
            old_snapshot=old_snapshot,
            new_snapshot=serialize_trip_admin(trip),
            reason=body.reason or "Trip rejected.",
        )

        await self.session.commit()

        return trip_to_resource(trip).model_dump(mode="json"), self._response_headers(trip)

    async def edit_trip(
        self, trip_id: str, body: EditTripRequest, if_match: str | None = None
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Edit trip fields."""
        trip = await _get_trip_or_404(self.session, trip_id)
        if not if_match:
            raise trip_if_match_required()
        parsed_version = parse_etag_version(if_match)
        if parsed_version is None or parsed_version != trip.version:
            raise trip_version_mismatch()

        normalized_status = normalize_trip_status(trip.status)
        if normalized_status not in {TripStatus.PENDING_REVIEW.value, TripStatus.COMPLETED.value}:
            raise invalid_status_transition(f"Cannot edit trip in {normalized_status} state.")

        old_snapshot = serialize_trip_admin(trip)
        update_data = body.model_dump(exclude_unset=True)

        _maybe_require_change_reason(self.auth, body, trip, update_data.get("driver_id"))

        candidate_driver_id = update_data.get("driver_id", trip.driver_id)
        candidate_vehicle_id = update_data.get("vehicle_id", trip.vehicle_id)
        candidate_trailer_id = update_data.get("trailer_id", trip.trailer_id)

        if {"driver_id", "vehicle_id", "trailer_id"} & update_data.keys():
            await ensure_trip_references_valid(
                driver_id=candidate_driver_id if isinstance(candidate_driver_id, str) else None,
                vehicle_id=candidate_vehicle_id,
                trailer_id=candidate_trailer_id,
            )

        candidate_tare = update_data.get("tare_weight_kg", trip.tare_weight_kg)
        candidate_gross = update_data.get("gross_weight_kg", trip.gross_weight_kg)
        candidate_net = update_data.get("net_weight_kg", trip.net_weight_kg)
        if {"tare_weight_kg", "gross_weight_kg", "net_weight_kg"} & update_data.keys():
            _validate_trip_weights(candidate_tare, candidate_gross, candidate_net)

        changed_fields: list[str] = []
        now = datetime.now(UTC)

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

        for field_name in (
            "driver_id",
            "vehicle_id",
            "trailer_id",
            "tare_weight_kg",
            "gross_weight_kg",
            "net_weight_kg",
        ):
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
            return trip_to_resource(trip).model_dump(mode="json"), self._response_headers(trip)

        if trip.status == TripStatus.COMPLETED or trip.source_type in (
            SourceType.ADMIN_MANUAL,
            SourceType.EMPTY_RETURN_ADMIN,
            SourceType.EXCEL_IMPORT,
        ):
            _ensure_complete_for_completion(trip)

        overlap_fields = {"driver_id", "vehicle_id", "trailer_id", "trip_datetime_utc", "route_pair_id"}
        if overlap_fields & set(changed_fields):
            await assert_no_trip_overlap(
                self.session,
                driver_id=trip.driver_id,
                vehicle_id=trip.vehicle_id,
                trailer_id=trip.trailer_id,
                trip_start_utc=trip.trip_datetime_utc,
                planned_end_utc=trip.planned_end_utc
                if trip.planned_end_utc is not None
                else (trip.trip_datetime_utc + timedelta(hours=24)),
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
        self.session.add(
            TripTripTimeline(
                id=_generate_id(),
                trip_id=trip.id,
                event_type="TRIP_EDITED",
                actor_type=_coerce_actor_type(self.auth.role),
                actor_id=self.auth.actor_id,
                note=update_data.get("note") or f"Trip edited: {', '.join(changed_fields)}",
                payload_json=json.dumps({"changed_fields": changed_fields}),
                created_at_utc=now,
            )
        )

        await _write_audit(
            self.session,
            trip_id=trip.id,
            action_type="UPDATE",
            actor_id=self.auth.actor_id,
            actor_role=str(self.auth.role),
            old_snapshot=old_snapshot,
            new_snapshot=serialize_trip_admin(trip),
            changed_fields=changed_fields,
            reason=update_data.get("change_reason"),
        )

        await self.session.commit()
        return trip_to_resource(trip).model_dump(mode="json"), self._response_headers(trip)

    async def create_empty_return(
        self,
        base_trip_id: str,
        body: EmptyReturnRequest,
        idempotency_key: str | None = None,
        legacy_idempotency_key: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Create an empty-return trip based on an existing trip."""
        effective_key = _resolve_idempotency_key(idempotency_key, legacy_idempotency_key)
        request_body = body.model_dump(exclude_none=True)
        request_hash = _merged_payload_hash(request_body)
        endpoint_fp = f"create_empty_return:{self.auth.actor_id}"

        replay = await _check_idempotency_key(self.session, effective_key, endpoint_fp, request_hash)
        if replay is not None:
            raw_body = replay.body
            if isinstance(raw_body, bytes):
                body_content = json.loads(raw_body)
            elif isinstance(raw_body, str):
                body_content = json.loads(raw_body)
            else:
                body_content = json.loads(str(raw_body))
            return body_content, self._normalize_replay_headers(dict(replay.headers))

        base_trip = await _get_trip_or_404(self.session, base_trip_id)
        if base_trip.is_empty_return:
            raise invalid_base_for_empty_return("Base trip is itself an empty return.")
        if (
            is_deleted_trip_status(base_trip.status)
            or normalize_trip_status(base_trip.status) == TripStatus.REJECTED.value
        ):
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
        status, review_reason = await _classify_manual_status(self.auth, trip_start_utc)
        now = datetime.now(UTC)
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
            created_by_actor_type=_coerce_actor_type(self.auth.role),
            created_by_actor_id=self.auth.actor_id,
            created_at_utc=now,
            updated_at_utc=now,
        )
        apply_trip_context(trip, context, reverse=True)
        await assert_no_trip_overlap(
            self.session,
            driver_id=trip.driver_id,
            vehicle_id=trip.vehicle_id,
            trailer_id=trip.trailer_id,
            trip_start_utc=trip.trip_datetime_utc,
            planned_end_utc=trip.planned_end_utc
            if trip.planned_end_utc is not None
            else (trip.trip_datetime_utc + timedelta(hours=24)),
        )
        self.session.add(trip)
        self.session.add(
            TripTripEvidence(
                id=_generate_id(),
                trip_id=trip_id,
                evidence_source=EvidenceSource.ADMIN_MANUAL,
                evidence_kind=EvidenceKind.MANUAL_ENTRY,
                raw_payload_json=_ensure_payload_size(json.dumps(request_body, default=str)),
                created_at_utc=now,
            )
        )
        self.session.add(
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
        self.session.add(
            TripTripTimeline(
                id=_generate_id(),
                trip_id=trip.id,
                event_type="TRIP_CREATED",
                actor_type=_coerce_actor_type(self.auth.role),
                actor_id=self.auth.actor_id,
                note=body.note or "Empty-return trip created.",
                payload_json=json.dumps({"base_trip_id": base_trip.id}),
                created_at_utc=now,
            )
        )
        await _create_outbox_event(self.session, trip, "trip.created.v1")
        TRIP_CREATED_TOTAL.labels(source_type=trip.source_type, **get_standard_labels()).inc()

        if trip.status == TripStatus.COMPLETED:
            await _create_outbox_event(self.session, trip, "trip.completed.v1")
            TRIP_COMPLETED_TOTAL.labels(**get_standard_labels()).inc()

        try:
            await self.session.commit()
        except IntegrityError as exc:
            raise _map_integrity_error(exc, trip_no=trip.trip_no) from exc

        resource_dict = trip_to_resource(trip).model_dump(mode="json")
        headers = self._response_headers(trip)

        if effective_key:
            await _save_idempotency_record(
                self.session,
                idempotency_key=effective_key,
                endpoint_fingerprint=endpoint_fp,
                request_hash=request_hash,
                response_status=201,
                response_body=resource_dict,
                response_headers=headers,
            )
        return resource_dict, headers
