"""Trailer service — business logic for all 12 trailer endpoints (Phase E).

Mirrors vehicle_service.py + vehicle_spec_service.py for trailers.
Orchestrates repositories, writes timeline + outbox events within the same transaction.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from fleet_service.auth import AuthContext
from fleet_service.config import settings
from fleet_service.constraint_error_mapper import map_integrity_error
from fleet_service.domain.enums import (
    AggregateType,
    DeleteResult,
    MasterStatus,
    ReferenceCheckStatus,
)
from platform_common import OutboxPublishStatus
from fleet_service.domain.etag import generate_master_etag, generate_spec_etag, parse_master_etag, parse_spec_etag
from fleet_service.domain.idempotency import compute_endpoint_fingerprint, compute_request_hash
from fleet_service.domain.normalization import normalize_plate
from fleet_service.errors import (
    AssetAlreadyInTargetStateError,
    AssetInactiveOrDeletedError,
    AssetReferencedHardDeleteForbiddenError,
    DependencyUnavailableError,
    EtagMismatchError,
    EtagRequiredError,
    IdempotencyHashMismatchError,
    IdempotencyKeyRequiredError,
    InvalidStatusTransitionError,
    SpecEtagMismatchError,
    SpecNotFoundForInstantError,
    SpecNotInitializedError,
    SpecVersionOverlapError,
    TrailerAssetCodeAlreadyExistsError,
    TrailerNotFoundError,
    TrailerPlateAlreadyExistsError,
    TrailerSoftDeletedError,
)
from fleet_service.models import (
    FleetAssetDeleteAudit,
    FleetAssetTimelineEvent,
    FleetIdempotencyRecord,
    FleetOutbox,
    FleetTrailer,
    FleetTrailerSpecVersion,
)
from fleet_service.repositories import (
    delete_audit_repo,
    idempotency_repo,
    outbox_repo,
    timeline_repo,
    trailer_repo,
    trailer_spec_repo,
)
from fleet_service.schemas.requests import TrailerCreateRequest, TrailerPatchRequest, TrailerSpecVersionRequest
from fleet_service.schemas.responses import (
    PagedResponse,
    TrailerCurrentSpecSummary,
    TrailerDetailResponse,
    TrailerListItemResponse,
    TrailerSpecResponse,
)
from fleet_service.timestamps import to_utc_naive, utc_now_naive

logger = logging.getLogger("fleet_service.trailer_service")

_TRAILER_CREATE_FINGERPRINT = compute_endpoint_fingerprint("POST", "/api/v1/trailers")
_IDEMPOTENCY_TTL_HOURS = 72


def _utc_now() -> datetime.datetime:
    """Return the current naive UTC timestamp for the Fleet schema."""
    return utc_now_naive()


def serialize_trailer_admin(trailer: FleetTrailer) -> dict[str, Any]:
    """Helper for timeline snapshots."""
    return {
        "trailer_id": trailer.trailer_id,
        "asset_code": trailer.asset_code,
        "plate_raw_current": trailer.plate_raw_current,
        "normalized_plate_current": trailer.normalized_plate_current,
        "brand": trailer.brand,
        "model": trailer.model,
        "model_year": trailer.model_year,
        "ownership_type": trailer.ownership_type,
        "status": trailer.status,
    }


# === CREATE ===


async def create_trailer(
    session: AsyncSession,
    body: TrailerCreateRequest,
    auth: AuthContext,
    *,
    idempotency_key: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
) -> tuple[TrailerDetailResponse, str, int]:
    """Create a trailer (idempotent, 11-step transaction).

    Returns (response, etag, status_code).
    """
    if not idempotency_key:
        raise IdempotencyKeyRequiredError()

    now = _utc_now()

    request_hash = compute_request_hash(body.model_dump())
    existing = await idempotency_repo.find_existing_record(session, idempotency_key, _TRAILER_CREATE_FINGERPRINT)
    if existing:
        if existing.request_hash != request_hash:
            raise IdempotencyHashMismatchError()
        cached = existing.response_body_json
        return (
            TrailerDetailResponse(**cached),
            generate_master_etag("TRAILER", cached["trailer_id"], cached["row_version"]),
            existing.response_status_code,
        )

    normalized_plate = normalize_plate(body.plate)

    if not await trailer_repo.check_asset_code_uniqueness(session, body.asset_code):
        raise TrailerAssetCodeAlreadyExistsError()
    if not await trailer_repo.check_plate_uniqueness(session, normalized_plate):
        raise TrailerPlateAlreadyExistsError()

    trailer_id = str(ULID())
    trailer = FleetTrailer(
        trailer_id=trailer_id,
        asset_code=body.asset_code,
        plate_raw_current=body.plate,
        normalized_plate_current=normalized_plate,
        brand=body.brand,
        model=body.model,
        model_year=body.model_year,
        ownership_type=body.ownership_type,
        status=MasterStatus.ACTIVE,
        notes=body.notes,
        row_version=1,
        spec_stream_version=0,
        created_at_utc=now,
        created_by_actor_type=auth.actor_type,
        created_by_actor_id=auth.actor_id,
        updated_at_utc=now,
        updated_by_actor_type=auth.actor_type,
        updated_by_actor_id=auth.actor_id,
    )

    # Step 6: INSERT Master & Spec
    current_spec = None
    try:
        await trailer_repo.create_trailer(session, trailer)
        if body.initial_spec is not None:
            trailer.spec_stream_version = 1
            effective_from = (
                to_utc_naive(body.initial_spec.effective_from_utc) if body.initial_spec.effective_from_utc else now
            )
            current_spec = FleetTrailerSpecVersion(
                trailer_spec_version_id=str(ULID()),
                trailer_id=trailer_id,
                version_no=1,
                effective_from_utc=effective_from,
                is_current=True,
                trailer_type=body.initial_spec.trailer_type,
                body_type=body.initial_spec.body_type,
                tare_weight_kg=body.initial_spec.tare_weight_kg,
                max_payload_kg=body.initial_spec.max_payload_kg,
                axle_count=body.initial_spec.axle_count,
                lift_axle_present=body.initial_spec.lift_axle_present,
                body_height_mm=body.initial_spec.body_height_mm,
                body_length_mm=body.initial_spec.body_length_mm,
                body_width_mm=body.initial_spec.body_width_mm,
                tire_rr_class=body.initial_spec.tire_rr_class,
                tire_type=body.initial_spec.tire_type,
                side_skirts_present=body.initial_spec.side_skirts_present,
                rear_tail_present=body.initial_spec.rear_tail_present,
                gap_reducer_present=body.initial_spec.gap_reducer_present,
                wheel_covers_present=body.initial_spec.wheel_covers_present,
                reefer_unit_present=body.initial_spec.reefer_unit_present,
                reefer_unit_type=body.initial_spec.reefer_unit_type,
                reefer_power_source=body.initial_spec.reefer_power_source,
                aero_package_level=body.initial_spec.aero_package_level,
                change_reason=body.initial_spec.change_reason,
                created_at_utc=now,
                created_by_actor_type=auth.actor_type,
                created_by_actor_id=auth.actor_id,
            )
            await trailer_spec_repo.insert_spec_version(session, current_spec)

        await session.flush()
    except IntegrityError as exc:
        raise map_integrity_error(exc, "TRAILER") from exc

    trailer_snapshot = serialize_trailer_admin(trailer)
    event_id = str(ULID())

    await timeline_repo.insert_timeline_event(
        session,
        FleetAssetTimelineEvent(
            event_id=event_id,
            aggregate_type=AggregateType.TRAILER,
            aggregate_id=trailer_id,
            event_type="fleet.trailer.created.v1",
            actor_type=auth.actor_type,
            actor_id=auth.actor_id,
            request_id=request_id,
            correlation_id=correlation_id,
            occurred_at_utc=now,
            payload_json={"snapshot": trailer_snapshot},
        ),
    )

    # Step 8: Outbox event (Enriched)
    outbox_event = FleetOutbox(
        outbox_id=str(ULID()),
        aggregate_type=AggregateType.TRAILER,
        aggregate_id=trailer_id,
        event_name="fleet.trailer.created.v1",
        event_version=settings.schema_event_version,
        partition_key=trailer_id,
        payload_json=json.dumps(
            {
                "event_id": event_id,
                "event_name": "fleet.trailer.created.v1",
                "event_version": settings.schema_event_version,
                "occurred_at_utc": now.isoformat(),
                "aggregate_type": "TRAILER",
                "aggregate_id": trailer_id,
                "row_version": 1,
                "request_id": request_id,
                "correlation_id": correlation_id,
                "data": trailer_snapshot,
            }
        ),
        publish_status=OutboxPublishStatus.PENDING,
        next_attempt_at_utc=now,
        created_at_utc=now,
    )
    await outbox_repo.insert_outbox_event(session, outbox_event)
    await session.commit()

    response = _build_trailer_detail_response(trailer, current_spec=current_spec)

    idem_record = FleetIdempotencyRecord(
        idempotency_key=idempotency_key,
        endpoint_fingerprint=_TRAILER_CREATE_FINGERPRINT,
        request_hash=request_hash,
        response_status_code=201,
        response_body_json=response.model_dump(mode="json"),
        resource_type="TRAILER",
        resource_id=trailer_id,
        created_at_utc=now,
        expires_at_utc=now + datetime.timedelta(hours=_IDEMPOTENCY_TTL_HOURS),
    )
    await idempotency_repo.insert_record(session, idem_record)
    # committed above

    etag = generate_master_etag("TRAILER", trailer_id, 1)
    return response, etag, 201


# === LIST ===


async def list_trailers(
    session: AsyncSession,
    *,
    status: str | None = None,
    ownership_type: str | None = None,
    q: str | None = None,
    sort: str = "updated_at_desc",
    page: int = 1,
    per_page: int = 20,
    include_inactive: bool = False,
    include_soft_deleted: bool = False,
) -> PagedResponse:
    """List trailers with filters, sort, pagination."""
    items, total = await trailer_repo.get_trailer_list(
        session,
        status=status,
        ownership_type=ownership_type,
        q=q,
        sort=sort,
        page=page,
        per_page=per_page,
        include_inactive=include_inactive,
        include_soft_deleted=include_soft_deleted,
    )
    total_pages = max(1, (total + per_page - 1) // per_page)
    return PagedResponse(
        items=[_build_trailer_list_response(t) for t in items],
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
    )


# === DETAIL ===


async def get_trailer_detail(session: AsyncSession, trailer_id: str) -> tuple[TrailerDetailResponse, str]:
    """Get trailer detail with current spec summary.

    Returns (response, etag).
    """
    trailer = await trailer_repo.get_trailer_by_id(session, trailer_id, include_soft_deleted=True)
    if not trailer:
        raise TrailerNotFoundError(trailer_id)

    current_spec = await trailer_repo.get_current_trailer_spec(session, trailer_id)
    response = _build_trailer_detail_response(trailer, current_spec)
    etag = generate_master_etag("TRAILER", trailer_id, trailer.row_version)
    await session.commit()
    return response, etag


# === PATCH ===


async def patch_trailer(
    session: AsyncSession,
    trailer_id: str,
    body: TrailerPatchRequest,
    auth: AuthContext,
    *,
    if_match: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
) -> tuple[TrailerDetailResponse, str]:
    """PATCH trailer with optimistic locking (master ETag).

    Returns (response, new_etag).
    """
    if not if_match:
        raise EtagRequiredError("master")

    parsed = parse_master_etag(if_match)
    if not parsed:
        raise EtagMismatchError()
    _, _, expected_version = parsed

    trailer = await trailer_repo.get_trailer_for_update(session, trailer_id)
    if not trailer:
        raise TrailerNotFoundError(trailer_id)
    if trailer.row_version != expected_version:
        raise EtagMismatchError()
    if trailer.soft_deleted_at_utc is not None:
        raise TrailerSoftDeletedError()

    from fleet_service.services.audit_helpers import _write_fleet_audit, serialize_trailer_admin

    old_snapshot = serialize_trailer_admin(trailer)

    now = _utc_now()
    changes: dict[str, Any] = {}

    if body.plate is not None:
        new_normalized = normalize_plate(body.plate)
        if not await trailer_repo.check_plate_uniqueness(session, new_normalized, exclude_trailer_id=trailer_id):
            raise TrailerPlateAlreadyExistsError()
        trailer.plate_raw_current = body.plate
        trailer.normalized_plate_current = new_normalized
        changes["plate"] = body.plate

    if body.brand is not None:
        trailer.brand = body.brand
        changes["brand"] = body.brand
    if body.model is not None:
        trailer.model = body.model
        changes["model"] = body.model
    if body.model_year is not None:
        trailer.model_year = body.model_year
        changes["model_year"] = body.model_year
    if body.ownership_type is not None:
        trailer.ownership_type = body.ownership_type
        changes["ownership_type"] = body.ownership_type
    if body.notes is not None:
        trailer.notes = body.notes
        changes["notes"] = body.notes

    trailer.row_version += 1
    trailer.updated_at_utc = now
    trailer.updated_by_actor_type = auth.actor_type
    trailer.updated_by_actor_id = auth.actor_id

    try:
        await trailer_repo.update_trailer(session, trailer)
    except IntegrityError as exc:
        raise map_integrity_error(exc, "TRAILER") from exc

    event_id = str(ULID())
    await timeline_repo.insert_timeline_event(
        session,
        FleetAssetTimelineEvent(
            event_id=event_id,
            aggregate_type=AggregateType.TRAILER,
            aggregate_id=trailer_id,
            event_type="fleet.trailer.updated.v1",
            actor_type=auth.actor_type,
            actor_id=auth.actor_id,
            request_id=request_id,
            correlation_id=correlation_id,
            occurred_at_utc=now,
            payload_json={"changes": changes, "row_version": trailer.row_version},
        ),
    )

    await outbox_repo.insert_outbox_event(
        session,
        FleetOutbox(
            outbox_id=str(ULID()),
            aggregate_type=AggregateType.TRAILER,
            aggregate_id=trailer_id,
            event_name="fleet.trailer.updated.v1",
            event_version=settings.schema_event_version,
            partition_key=trailer_id,
            payload_json=json.dumps(
                {
                    "event_id": event_id,
                    "event_name": "fleet.trailer.updated.v1",
                    "event_version": settings.schema_event_version,
                    "occurred_at_utc": now.isoformat(),
                    "aggregate_type": "TRAILER",
                    "aggregate_id": trailer_id,
                    "row_version": trailer.row_version,
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                }
            ),
            publish_status=OutboxPublishStatus.PENDING,
            next_attempt_at_utc=now,
            created_at_utc=now,
        ),
    )

    # High-fidelity audit
    await _write_fleet_audit(
        session,
        aggregate_type=AggregateType.TRAILER,
        aggregate_id=trailer_id,
        action_type="UPDATE",
        actor_id=auth.actor_id,
        actor_role=auth.actor_type,
        old_snapshot=old_snapshot,
        new_snapshot=serialize_trailer_admin(trailer),
        changed_fields=changes,
        reason=body.notes or f"Fields changed: {', '.join(changes.keys())}",
        request_id=request_id,
    )

    current_spec = await trailer_repo.get_current_trailer_spec(session, trailer_id)
    response = _build_trailer_detail_response(trailer, current_spec)
    etag = generate_master_etag("TRAILER", trailer_id, trailer.row_version)
    await session.commit()
    return response, etag


# === LIFECYCLE: DEACTIVATE / REACTIVATE / SOFT-DELETE ===


async def deactivate_trailer(
    session: AsyncSession,
    trailer_id: str,
    reason: str,
    auth: AuthContext,
    *,
    if_match: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
) -> tuple[TrailerDetailResponse, str]:
    """ACTIVE → INACTIVE."""
    return await _lifecycle_transition(
        session,
        trailer_id,
        reason,
        auth,
        target_status=MasterStatus.INACTIVE,
        valid_from={MasterStatus.ACTIVE},
        event_name="fleet.trailer.deactivated.v1",
        if_match=if_match,
        request_id=request_id,
        correlation_id=correlation_id,
    )


async def reactivate_trailer(
    session: AsyncSession,
    trailer_id: str,
    reason: str,
    auth: AuthContext,
    *,
    if_match: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
) -> tuple[TrailerDetailResponse, str]:
    """INACTIVE → ACTIVE."""
    return await _lifecycle_transition(
        session,
        trailer_id,
        reason,
        auth,
        target_status=MasterStatus.ACTIVE,
        valid_from={MasterStatus.INACTIVE},
        event_name="fleet.trailer.reactivated.v1",
        if_match=if_match,
        request_id=request_id,
        correlation_id=correlation_id,
    )


async def soft_delete_trailer(
    session: AsyncSession,
    trailer_id: str,
    reason: str,
    auth: AuthContext,
    *,
    if_match: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
) -> tuple[TrailerDetailResponse, str]:
    """Set soft_deleted_at_utc fields."""
    if not if_match:
        raise EtagRequiredError("master")

    parsed = parse_master_etag(if_match)
    if not parsed:
        raise EtagMismatchError()
    _, _, expected_version = parsed

    trailer = await trailer_repo.get_trailer_for_update(session, trailer_id)
    if not trailer:
        raise TrailerNotFoundError(trailer_id)
    if trailer.row_version != expected_version:
        raise EtagMismatchError()
    if trailer.soft_deleted_at_utc is not None:
        raise AssetAlreadyInTargetStateError("SOFT_DELETED")

    now = _utc_now()
    trailer.soft_deleted_at_utc = now
    trailer.soft_deleted_by_actor_type = auth.actor_type
    trailer.soft_deleted_by_actor_id = auth.actor_id
    trailer.soft_delete_reason = reason
    trailer.row_version += 1
    trailer.updated_at_utc = now
    trailer.updated_by_actor_type = auth.actor_type
    trailer.updated_by_actor_id = auth.actor_id

    await trailer_repo.update_trailer(session, trailer)

    event_id = str(ULID())
    await timeline_repo.insert_timeline_event(
        session,
        FleetAssetTimelineEvent(
            event_id=event_id,
            aggregate_type=AggregateType.TRAILER,
            aggregate_id=trailer_id,
            event_type="fleet.trailer.soft_deleted.v1",
            actor_type=auth.actor_type,
            actor_id=auth.actor_id,
            request_id=request_id,
            correlation_id=correlation_id,
            occurred_at_utc=now,
            payload_json={"reason": reason, "row_version": trailer.row_version},
        ),
    )

    await outbox_repo.insert_outbox_event(
        session,
        FleetOutbox(
            outbox_id=str(ULID()),
            aggregate_type=AggregateType.TRAILER,
            aggregate_id=trailer_id,
            event_name="fleet.trailer.soft_deleted.v1",
            event_version=settings.schema_event_version,
            partition_key=trailer_id,
            payload_json=json.dumps(
                {
                    "event_id": event_id,
                    "event_name": "fleet.trailer.soft_deleted.v1",
                    "event_version": settings.schema_event_version,
                    "occurred_at_utc": now.isoformat(),
                    "aggregate_type": "TRAILER",
                    "aggregate_id": trailer_id,
                    "row_version": trailer.row_version,
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                }
            ),
            publish_status=OutboxPublishStatus.PENDING,
            next_attempt_at_utc=now,
            created_at_utc=now,
        ),
    )

    current_spec = await trailer_repo.get_current_trailer_spec(session, trailer_id)
    response = _build_trailer_detail_response(trailer, current_spec)
    etag = generate_master_etag("TRAILER", trailer_id, trailer.row_version)
    await session.commit()
    return response, etag


# === HARD DELETE (4-stage) ===


async def hard_delete_trailer(
    session: AsyncSession,
    trailer_id: str,
    reason: str,
    auth: AuthContext,
    *,
    if_match: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
    trip_reference_checker: Any = None,
) -> dict[str, Any]:
    """Hard-delete with 4-stage pipeline."""
    now = _utc_now()

    if not if_match:
        raise EtagRequiredError("master")

    parsed = parse_master_etag(if_match)
    if not parsed:
        raise EtagMismatchError()
    _, _, expected_version = parsed

    # Stage 1: Non-locking pre-check
    trailer = await trailer_repo.get_trailer_by_id(session, trailer_id, include_soft_deleted=True)
    if not trailer:
        await _audit_hard_delete(
            session, trailer_id, None, auth, now, DeleteResult.REJECTED_NOT_FOUND, "Trailer not found", request_id
        )
        raise TrailerNotFoundError(trailer_id)
    if trailer.row_version != expected_version:
        await _audit_hard_delete(
            session, trailer_id, trailer, auth, now, DeleteResult.REJECTED_ETAG_MISMATCH, "ETag mismatch", request_id
        )
        raise EtagMismatchError()
    if trailer.soft_deleted_at_utc is None:
        await _audit_hard_delete(
            session,
            trailer_id,
            trailer,
            auth,
            now,
            DeleteResult.REJECTED_NOT_SOFT_DELETED,
            "Trailer must be soft-deleted before hard-delete",
            request_id,
        )
        raise InvalidStatusTransitionError("Trailer must be soft-deleted before hard-delete")

    # Stage 2: Trip reference-check
    ref_check_status = ReferenceCheckStatus.NOT_ATTEMPTED
    ref_check_json = None
    if trip_reference_checker:
        try:
            ref_result = await trip_reference_checker(trailer_id, "TRAILER")
            ref_check_status = ReferenceCheckStatus.SUCCEEDED
            ref_check_json = ref_result
            if ref_result.get("has_references", False):
                await _audit_hard_delete(
                    session,
                    trailer_id,
                    trailer,
                    auth,
                    now,
                    DeleteResult.REJECTED_REFERENCED,
                    "Trailer is referenced by trips",
                    request_id,
                    ref_check_status,
                    ref_check_json,
                )
                raise AssetReferencedHardDeleteForbiddenError()
        except AssetReferencedHardDeleteForbiddenError:
            raise
        except Exception:
            ref_check_status = ReferenceCheckStatus.DEPENDENCY_UNAVAILABLE
            await _audit_hard_delete(
                session,
                trailer_id,
                trailer,
                auth,
                now,
                DeleteResult.REJECTED_DEPENDENCY_UNAVAILABLE,
                "Trip service unavailable",
                request_id,
                ref_check_status,
            )
            raise DependencyUnavailableError("trip-service")

    # Stage 3: FOR UPDATE → re-verify → delete
    locked_trailer = await trailer_repo.get_trailer_for_update(session, trailer_id)
    if not locked_trailer:
        raise TrailerNotFoundError(trailer_id)
    if locked_trailer.row_version != expected_version:
        raise EtagMismatchError()
    if locked_trailer.soft_deleted_at_utc is None:
        raise InvalidStatusTransitionError("Trailer must be soft-deleted before hard-delete")

    await outbox_repo.dead_letter_by_aggregate(session, AggregateType.TRAILER, trailer_id)

    snapshot = _build_trailer_snapshot(locked_trailer)

    await trailer_repo.delete_trailer_spec_versions(session, trailer_id)
    await trailer_repo.hard_delete_trailer(session, locked_trailer)

    audit_id = str(ULID())
    await delete_audit_repo.insert_delete_audit(
        session,
        FleetAssetDeleteAudit(
            delete_audit_id=audit_id,
            aggregate_type=AggregateType.TRAILER,
            aggregate_id=trailer_id,
            snapshot_json=snapshot,
            reference_check_json=ref_check_json,
            reference_check_status=ref_check_status,
            delete_attempted_by_actor_type=auth.actor_type,
            delete_attempted_by_actor_id=auth.actor_id,
            delete_result=DeleteResult.SUCCEEDED,
            delete_result_reason=reason,
            created_at_utc=now,
        ),
    )

    event_id = str(ULID())
    await timeline_repo.insert_timeline_event(
        session,
        FleetAssetTimelineEvent(
            event_id=event_id,
            aggregate_type=AggregateType.TRAILER,
            aggregate_id=trailer_id,
            event_type="fleet.trailer.hard_deleted.v1",
            actor_type=auth.actor_type,
            actor_id=auth.actor_id,
            request_id=request_id,
            correlation_id=correlation_id,
            occurred_at_utc=now,
            payload_json={"reason": reason, "snapshot_json": snapshot},
        ),
    )

    await outbox_repo.insert_outbox_event(
        session,
        FleetOutbox(
            outbox_id=str(ULID()),
            aggregate_type=AggregateType.TRAILER,
            aggregate_id=trailer_id,
            event_name="fleet.trailer.hard_deleted.v1",
            event_version=settings.schema_event_version,
            partition_key=trailer_id,
            payload_json=json.dumps(
                {
                    "event_id": event_id,
                    "event_name": "fleet.trailer.hard_deleted.v1",
                    "event_version": settings.schema_event_version,
                    "occurred_at_utc": now.isoformat(),
                    "aggregate_type": "TRAILER",
                    "aggregate_id": trailer_id,
                    "snapshot_json": snapshot,
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                }
            ),
            publish_status=OutboxPublishStatus.PENDING,
            next_attempt_at_utc=now,
            created_at_utc=now,
        ),
    )

    await session.commit()

    return {"deleted": True, "aggregate_type": "TRAILER", "aggregate_id": trailer_id, "delete_audit_id": audit_id}


# === TIMELINE ===


async def get_trailer_timeline(
    session: AsyncSession,
    trailer_id: str,
    *,
    page: int = 1,
    per_page: int = 50,
) -> list[dict[str, Any]]:
    """Get trailer timeline events."""
    events = await timeline_repo.get_timeline_by_aggregate(
        session, AggregateType.TRAILER, trailer_id, page=page, per_page=per_page
    )
    if not events:
        trailer = await trailer_repo.get_trailer_by_id(session, trailer_id, include_soft_deleted=True)
        if not trailer:
            raise TrailerNotFoundError(trailer_id)
    return [
        {
            "event_id": e.event_id,
            "aggregate_type": e.aggregate_type,
            "aggregate_id": e.aggregate_id,
            "event_type": e.event_type,
            "actor_type": e.actor_type,
            "actor_id": e.actor_id,
            "request_id": e.request_id,
            "correlation_id": e.correlation_id,
            "occurred_at_utc": e.occurred_at_utc.isoformat(),
            "payload": e.payload_json,
        }
        for e in events
    ]


# === SPEC VERSION — CREATE ===


async def create_trailer_spec_version(
    session: AsyncSession,
    trailer_id: str,
    body: TrailerSpecVersionRequest,
    auth: AuthContext,
    *,
    if_match: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
) -> tuple[TrailerSpecResponse, str, int]:
    """Create a new trailer spec version (13-step sequence).

    Returns (response, spec_etag, status_code).
    """
    if not if_match:
        raise EtagRequiredError("spec")

    parsed = parse_spec_etag(if_match)
    if not parsed:
        raise SpecEtagMismatchError()
    _, _, expected_spec_version = parsed

    trailer = await trailer_repo.get_trailer_for_update(session, trailer_id)
    if not trailer:
        raise TrailerNotFoundError(trailer_id)
    if trailer.soft_deleted_at_utc is not None or trailer.status != "ACTIVE":
        raise AssetInactiveOrDeletedError()
    if trailer.spec_stream_version != expected_spec_version:
        raise SpecEtagMismatchError()

    now = _utc_now()
    effective_from = to_utc_naive(body.effective_from_utc) if body.effective_from_utc else now

    max_version = await trailer_spec_repo.get_max_version_no(session, trailer_id)
    new_version_no = max_version + 1

    spec_version_id = str(ULID())
    spec = FleetTrailerSpecVersion(
        trailer_spec_version_id=spec_version_id,
        trailer_id=trailer_id,
        version_no=new_version_no,
        effective_from_utc=effective_from,
        effective_to_utc=None,
        is_current=True,
        trailer_type=body.trailer_type,
        body_type=body.body_type,
        tare_weight_kg=body.tare_weight_kg,
        max_payload_kg=body.max_payload_kg,
        axle_count=body.axle_count,
        lift_axle_present=body.lift_axle_present,
        body_height_mm=body.body_height_mm,
        body_length_mm=body.body_length_mm,
        body_width_mm=body.body_width_mm,
        tire_rr_class=body.tire_rr_class,
        tire_type=body.tire_type,
        side_skirts_present=body.side_skirts_present,
        rear_tail_present=body.rear_tail_present,
        gap_reducer_present=body.gap_reducer_present,
        wheel_covers_present=body.wheel_covers_present,
        reefer_unit_present=body.reefer_unit_present,
        reefer_unit_type=body.reefer_unit_type,
        reefer_power_source=body.reefer_power_source,
        aero_package_level=body.aero_package_level,
        change_reason=body.change_reason,
        created_at_utc=now,
        created_by_actor_type=auth.actor_type,
        created_by_actor_id=auth.actor_id,
    )

    try:
        await trailer_spec_repo.close_current_spec(session, trailer_id, effective_from)
        await trailer_spec_repo.insert_spec_version(session, spec)
    except IntegrityError as exc:
        mapped = map_integrity_error(exc, "TRAILER")
        if mapped:
            raise mapped from exc
        raise SpecVersionOverlapError() from exc

    trailer.spec_stream_version += 1
    trailer.updated_at_utc = now
    trailer.updated_by_actor_type = auth.actor_type
    trailer.updated_by_actor_id = auth.actor_id
    await trailer_repo.update_trailer(session, trailer)

    event_id = str(ULID())
    await timeline_repo.insert_timeline_event(
        session,
        FleetAssetTimelineEvent(
            event_id=event_id,
            aggregate_type=AggregateType.TRAILER,
            aggregate_id=trailer_id,
            event_type="fleet.trailer.spec_version_created.v1",
            actor_type=auth.actor_type,
            actor_id=auth.actor_id,
            request_id=request_id,
            correlation_id=correlation_id,
            occurred_at_utc=now,
            payload_json={
                "trailer_spec_version_id": spec_version_id,
                "version_no": new_version_no,
                "change_reason": body.change_reason,
                "spec_stream_version": trailer.spec_stream_version,
            },
        ),
    )

    await outbox_repo.insert_outbox_event(
        session,
        FleetOutbox(
            outbox_id=str(ULID()),
            aggregate_type=AggregateType.TRAILER,
            aggregate_id=trailer_id,
            event_name="fleet.trailer.spec_version_created.v1",
            event_version=settings.schema_event_version,
            partition_key=trailer_id,
            payload_json=json.dumps(
                {
                    "event_id": event_id,
                    "event_name": "fleet.trailer.spec_version_created.v1",
                    "event_version": settings.schema_event_version,
                    "occurred_at_utc": now.isoformat(),
                    "aggregate_type": "TRAILER",
                    "aggregate_id": trailer_id,
                    "trailer_spec_version_id": spec_version_id,
                    "version_no": new_version_no,
                    "spec_stream_version": trailer.spec_stream_version,
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                }
            ),
            publish_status=OutboxPublishStatus.PENDING,
            next_attempt_at_utc=now,
            created_at_utc=now,
        ),
    )

    response = _build_spec_response(spec)
    etag = generate_spec_etag("TRAILER", trailer_id, trailer.spec_stream_version)
    await session.commit()
    return response, etag, 201


# === SPEC VERSION — GET CURRENT ===


async def get_current_spec(
    session: AsyncSession,
    trailer_id: str,
) -> tuple[TrailerSpecResponse, str]:
    """Get the current spec version for a trailer."""
    trailer = await trailer_repo.get_trailer_by_id(session, trailer_id, include_soft_deleted=True)
    if not trailer:
        raise TrailerNotFoundError(trailer_id)

    spec = await trailer_spec_repo.get_current_spec(session, trailer_id)
    if not spec:
        raise SpecNotInitializedError("TRAILER")

    response = _build_spec_response(spec)
    etag = generate_spec_etag("TRAILER", trailer_id, trailer.spec_stream_version)
    await session.commit()
    return response, etag


# === SPEC VERSION — GET AS-OF ===


async def get_spec_as_of(
    session: AsyncSession,
    trailer_id: str,
    at: datetime.datetime,
) -> TrailerSpecResponse:
    """Get the spec version effective at a given timestamp."""
    trailer = await trailer_repo.get_trailer_by_id(session, trailer_id, include_soft_deleted=True)
    if not trailer:
        raise TrailerNotFoundError(trailer_id)

    spec = await trailer_spec_repo.get_spec_as_of(session, trailer_id, to_utc_naive(at))
    if not spec:
        raise SpecNotFoundForInstantError(at.isoformat())

    return _build_spec_response(spec)


# === INTERNAL HELPERS ===


async def _lifecycle_transition(
    session: AsyncSession,
    trailer_id: str,
    reason: str,
    auth: AuthContext,
    *,
    target_status: str,
    valid_from: set[str],
    event_name: str,
    if_match: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
) -> tuple[TrailerDetailResponse, str]:
    """Generic lifecycle transition (deactivate/reactivate)."""
    if not if_match:
        raise EtagRequiredError("master")

    parsed = parse_master_etag(if_match)
    if not parsed:
        raise EtagMismatchError()
    _, _, expected_version = parsed

    trailer = await trailer_repo.get_trailer_for_update(session, trailer_id)
    if not trailer:
        raise TrailerNotFoundError(trailer_id)
    if trailer.row_version != expected_version:
        raise EtagMismatchError()
    if trailer.soft_deleted_at_utc is not None:
        raise TrailerSoftDeletedError()

    if trailer.status == target_status:
        raise AssetAlreadyInTargetStateError(target_status)
    if trailer.status not in valid_from:
        raise InvalidStatusTransitionError(f"Cannot transition from {trailer.status} to {target_status}")

    now = _utc_now()
    trailer.status = target_status
    trailer.row_version += 1
    trailer.updated_at_utc = now
    trailer.updated_by_actor_type = auth.actor_type
    trailer.updated_by_actor_id = auth.actor_id

    await trailer_repo.update_trailer(session, trailer)

    event_id = str(ULID())
    await timeline_repo.insert_timeline_event(
        session,
        FleetAssetTimelineEvent(
            event_id=event_id,
            aggregate_type=AggregateType.TRAILER,
            aggregate_id=trailer_id,
            event_type=event_name,
            actor_type=auth.actor_type,
            actor_id=auth.actor_id,
            request_id=request_id,
            correlation_id=correlation_id,
            occurred_at_utc=now,
            payload_json={"reason": reason, "new_status": target_status, "row_version": trailer.row_version},
        ),
    )

    await outbox_repo.insert_outbox_event(
        session,
        FleetOutbox(
            outbox_id=str(ULID()),
            aggregate_type=AggregateType.TRAILER,
            aggregate_id=trailer_id,
            event_name=event_name,
            event_version=settings.schema_event_version,
            partition_key=trailer_id,
            payload_json=json.dumps(
                {
                    "event_id": event_id,
                    "event_name": event_name,
                    "event_version": settings.schema_event_version,
                    "occurred_at_utc": now.isoformat(),
                    "aggregate_type": "TRAILER",
                    "aggregate_id": trailer_id,
                    "new_status": target_status,
                    "row_version": trailer.row_version,
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                }
            ),
            publish_status=OutboxPublishStatus.PENDING,
            next_attempt_at_utc=now,
            created_at_utc=now,
        ),
    )

    current_spec = await trailer_repo.get_current_trailer_spec(session, trailer_id)
    response = _build_trailer_detail_response(trailer, current_spec)
    etag = generate_master_etag("TRAILER", trailer_id, trailer.row_version)
    await session.commit()
    return response, etag


async def _audit_hard_delete(
    session: AsyncSession,
    trailer_id: str,
    trailer: FleetTrailer | None,
    auth: AuthContext,
    now: datetime.datetime,
    result: str,
    reason: str,
    request_id: str | None = None,
    ref_check_status: str = ReferenceCheckStatus.NOT_ATTEMPTED,
    ref_check_json: dict[str, Any] | None = None,
) -> None:
    """Write a delete audit row for any rejection/success path."""
    snapshot = _build_trailer_snapshot(trailer) if trailer else {}
    await delete_audit_repo.insert_delete_audit(
        session,
        FleetAssetDeleteAudit(
            delete_audit_id=str(ULID()),
            aggregate_type=AggregateType.TRAILER,
            aggregate_id=trailer_id,
            snapshot_json=snapshot,
            reference_check_json=ref_check_json,
            reference_check_status=ref_check_status,
            delete_attempted_by_actor_type=auth.actor_type,
            delete_attempted_by_actor_id=auth.actor_id,
            delete_result=result,
            delete_result_reason=reason,
            created_at_utc=now,
        ),
    )


def _build_trailer_detail_response(trailer: FleetTrailer, current_spec: Any | None) -> TrailerDetailResponse:
    """Build a TrailerDetailResponse from ORM model."""
    is_selectable = trailer.soft_deleted_at_utc is None and trailer.status == MasterStatus.ACTIVE
    spec_summary = None
    if current_spec:
        spec_summary = TrailerCurrentSpecSummary(
            version_no=current_spec.version_no,
            trailer_type=current_spec.trailer_type,
            body_type=current_spec.body_type,
            tare_weight_kg=current_spec.tare_weight_kg,
            max_payload_kg=current_spec.max_payload_kg,
            effective_from_utc=current_spec.effective_from_utc,
        )
    return TrailerDetailResponse(
        trailer_id=trailer.trailer_id,
        asset_code=trailer.asset_code,
        plate_raw_current=trailer.plate_raw_current,
        normalized_plate_current=trailer.normalized_plate_current,
        brand=trailer.brand,
        model=trailer.model,
        model_year=trailer.model_year,
        ownership_type=trailer.ownership_type,
        status=trailer.status,
        lifecycle_state=trailer.lifecycle_state,
        notes=trailer.notes,
        row_version=trailer.row_version,
        spec_stream_version=trailer.spec_stream_version,
        is_selectable=is_selectable,
        current_spec_summary=spec_summary,
        created_at_utc=trailer.created_at_utc,
        created_by_actor_type=trailer.created_by_actor_type,
        created_by_actor_id=trailer.created_by_actor_id,
        updated_at_utc=trailer.updated_at_utc,
        updated_by_actor_type=trailer.updated_by_actor_type,
        updated_by_actor_id=trailer.updated_by_actor_id,
        soft_deleted_at_utc=trailer.soft_deleted_at_utc,
        soft_deleted_by_actor_type=trailer.soft_deleted_by_actor_type,
        soft_deleted_by_actor_id=trailer.soft_deleted_by_actor_id,
        soft_delete_reason=trailer.soft_delete_reason,
    )


def _build_trailer_list_response(trailer: FleetTrailer) -> TrailerListItemResponse:
    """Build a TrailerListItemResponse from ORM model."""
    is_selectable = trailer.soft_deleted_at_utc is None and trailer.status == MasterStatus.ACTIVE
    return TrailerListItemResponse(
        trailer_id=trailer.trailer_id,
        asset_code=trailer.asset_code,
        plate_raw_current=trailer.plate_raw_current,
        normalized_plate_current=trailer.normalized_plate_current,
        brand=trailer.brand,
        model=trailer.model,
        model_year=trailer.model_year,
        ownership_type=trailer.ownership_type,
        status=trailer.status,
        lifecycle_state=trailer.lifecycle_state,
        row_version=trailer.row_version,
        spec_stream_version=trailer.spec_stream_version,
        is_selectable=is_selectable,
        created_at_utc=trailer.created_at_utc,
        updated_at_utc=trailer.updated_at_utc,
    )


def _build_trailer_snapshot(trailer: FleetTrailer) -> dict[str, Any]:
    """Build a snapshot dict for delete audit."""
    return {
        "trailer_id": trailer.trailer_id,
        "asset_code": trailer.asset_code,
        "plate_raw_current": trailer.plate_raw_current,
        "normalized_plate_current": trailer.normalized_plate_current,
        "brand": trailer.brand,
        "model": trailer.model,
        "model_year": trailer.model_year,
        "ownership_type": trailer.ownership_type,
        "status": trailer.status,
        "row_version": trailer.row_version,
        "spec_stream_version": trailer.spec_stream_version,
        "created_at_utc": trailer.created_at_utc.isoformat() if trailer.created_at_utc else None,
        "updated_at_utc": trailer.updated_at_utc.isoformat() if trailer.updated_at_utc else None,
    }


def _build_spec_response(spec: FleetTrailerSpecVersion) -> TrailerSpecResponse:
    """Build a TrailerSpecResponse from ORM model."""
    return TrailerSpecResponse(
        trailer_spec_version_id=spec.trailer_spec_version_id,
        trailer_id=spec.trailer_id,
        version_no=spec.version_no,
        effective_from_utc=spec.effective_from_utc,
        effective_to_utc=spec.effective_to_utc,
        is_current=spec.is_current,
        trailer_type=spec.trailer_type,
        body_type=spec.body_type,
        tare_weight_kg=spec.tare_weight_kg,
        max_payload_kg=spec.max_payload_kg,
        axle_count=spec.axle_count,
        lift_axle_present=spec.lift_axle_present,
        body_height_mm=spec.body_height_mm,
        body_length_mm=spec.body_length_mm,
        body_width_mm=spec.body_width_mm,
        tire_rr_class=spec.tire_rr_class,
        tire_type=spec.tire_type,
        side_skirts_present=spec.side_skirts_present,
        rear_tail_present=spec.rear_tail_present,
        gap_reducer_present=spec.gap_reducer_present,
        wheel_covers_present=spec.wheel_covers_present,
        reefer_unit_present=spec.reefer_unit_present,
        reefer_unit_type=spec.reefer_unit_type,
        reefer_power_source=spec.reefer_power_source,
        aero_package_level=spec.aero_package_level,
        change_reason=spec.change_reason,
        created_at_utc=spec.created_at_utc,
        created_by_actor_type=spec.created_by_actor_type,
        created_by_actor_id=spec.created_by_actor_id,
    )
