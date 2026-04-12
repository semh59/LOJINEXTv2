"""Vehicle service — business logic for all 9 vehicle endpoints.

Orchestrates repositories, writes timeline + outbox events within the same transaction.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any

from platform_common import OutboxPublishStatus
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
from fleet_service.domain.etag import generate_master_etag, generate_spec_etag
from fleet_service.domain.idempotency import compute_endpoint_fingerprint, compute_request_hash
from fleet_service.domain.normalization import normalize_plate
from fleet_service.errors import (
    AssetAlreadyInTargetStateError,
    AssetReferencedHardDeleteForbiddenError,
    DependencyUnavailableError,
    EtagMismatchError,
    EtagRequiredError,
    IdempotencyHashMismatchError,
    IdempotencyKeyRequiredError,
    InvalidStatusTransitionError,
    VehicleAssetCodeAlreadyExistsError,
    VehicleNotFoundError,
    VehiclePlateAlreadyExistsError,
    VehicleSoftDeletedError,
)
from fleet_service.models import (
    FleetAssetDeleteAudit,
    FleetAssetTimelineEvent,
    FleetIdempotencyRecord,
    FleetOutbox,
    FleetVehicle,
    FleetVehicleSpecVersion,
)
from fleet_service.repositories import (
    delete_audit_repo,
    idempotency_repo,
    outbox_repo,
    timeline_repo,
    vehicle_repo,
    vehicle_spec_repo,
)
from fleet_service.schemas.requests import VehicleCreateRequest, VehiclePatchRequest
from fleet_service.schemas.responses import (
    CurrentSpecSummary,
    PagedResponse,
    VehicleDetailResponse,
    VehicleListItemResponse,
)
from fleet_service.timestamps import to_utc_aware, utc_now_aware

logger = logging.getLogger("fleet_service.vehicle_service")

# Idempotency
_VEHICLE_CREATE_FINGERPRINT = compute_endpoint_fingerprint("POST", "/api/v1/vehicles")
_IDEMPOTENCY_TTL_HOURS = 72


def _utc_now() -> datetime.datetime:
    """Return the current naive UTC timestamp for the Fleet schema."""
    return utc_now_aware()


# === CREATE ===


async def create_vehicle(
    session: AsyncSession,
    body: VehicleCreateRequest,
    auth: AuthContext,
    *,
    idempotency_key: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
) -> tuple[VehicleDetailResponse, str, int, str | None]:
    """Create a vehicle (idempotent, 11-step transaction).

    Returns (response, etag, status_code, spec_etag).
    """
    # Step 1: Require idempotency key
    if not idempotency_key:
        raise IdempotencyKeyRequiredError()

    now = _utc_now()

    # Step 2: Idempotency replay check
    request_hash = compute_request_hash(body.model_dump())
    existing = await idempotency_repo.find_existing_record(session, idempotency_key, _VEHICLE_CREATE_FINGERPRINT)
    if existing:
        if existing.request_hash != request_hash:
            raise IdempotencyHashMismatchError()
        # Replay: return cached response
        cached = existing.response_body_json
        replay_spec_etag = None
        if cached.get("current_spec_summary") is not None:
            replay_spec_etag = generate_spec_etag("VEHICLE", cached["vehicle_id"], cached["spec_stream_version"])
        return (
            VehicleDetailResponse(**cached),
            generate_master_etag("VEHICLE", cached["vehicle_id"], cached["row_version"]),
            existing.response_status_code,
            replay_spec_etag,
        )

    # Step 3: Normalize plate
    normalized_plate = normalize_plate(body.plate)

    # Step 4: Uniqueness checks
    if not await vehicle_repo.check_asset_code_uniqueness(session, body.asset_code):
        raise VehicleAssetCodeAlreadyExistsError()
    if not await vehicle_repo.check_plate_uniqueness(session, normalized_plate):
        raise VehiclePlateAlreadyExistsError()

    # Step 5: Build entity
    vehicle_id = str(ULID())
    vehicle = FleetVehicle(
        vehicle_id=vehicle_id,
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
    try:
        current_spec = None
        await vehicle_repo.create_vehicle(session, vehicle)
        if body.initial_spec is not None:
            vehicle.spec_stream_version = 1
            effective_from = (
                to_utc_aware(body.initial_spec.effective_from_utc) if body.initial_spec.effective_from_utc else now
            )
            current_spec = FleetVehicleSpecVersion(
                vehicle_spec_version_id=str(ULID()),
                vehicle_id=vehicle_id,
                version_no=1,
                effective_from_utc=effective_from,
                is_current=True,
                fuel_type=body.initial_spec.fuel_type,
                powertrain_type=body.initial_spec.powertrain_type,
                engine_power_kw=body.initial_spec.engine_power_kw,
                engine_displacement_l=body.initial_spec.engine_displacement_l,
                emission_class=body.initial_spec.emission_class,
                transmission_type=body.initial_spec.transmission_type,
                gear_count=body.initial_spec.gear_count,
                final_drive_ratio=body.initial_spec.final_drive_ratio,
                axle_config=body.initial_spec.axle_config,
                total_axle_count=body.initial_spec.total_axle_count,
                driven_axle_count=body.initial_spec.driven_axle_count,
                curb_weight_kg=body.initial_spec.curb_weight_kg,
                gvwr_kg=body.initial_spec.gvwr_kg,
                gcwr_kg=body.initial_spec.gcwr_kg,
                payload_capacity_kg=body.initial_spec.payload_capacity_kg,
                tractor_cab_type=body.initial_spec.tractor_cab_type,
                roof_height_class=body.initial_spec.roof_height_class,
                aero_package_level=body.initial_spec.aero_package_level,
                tire_rr_class=body.initial_spec.tire_rr_class,
                tire_type=body.initial_spec.tire_type,
                speed_limiter_kph=body.initial_spec.speed_limiter_kph,
                pto_present=body.initial_spec.pto_present,
                apu_present=body.initial_spec.apu_present,
                idle_reduction_type=body.initial_spec.idle_reduction_type,
                first_registration_date=body.initial_spec.first_registration_date,
                in_service_date=body.initial_spec.in_service_date,
                change_reason=body.initial_spec.change_reason,
                created_at_utc=now,
                created_by_actor_type=auth.actor_type,
                created_by_actor_id=auth.actor_id,
            )
            await vehicle_spec_repo.insert_spec_version(session, current_spec)

        # CRITICAL: Flush to ensure DB state is stable before event generation
        await session.flush()
    except IntegrityError as exc:
        raise map_integrity_error(exc, "VEHICLE") from exc

    # Step 7: Timeline event
    from fleet_service.services.audit_helpers import serialize_vehicle_admin

    vehicle_snapshot = serialize_vehicle_admin(vehicle)
    event_id = str(ULID())

    timeline_event = FleetAssetTimelineEvent(
        event_id=event_id,
        aggregate_type=AggregateType.VEHICLE,
        aggregate_id=vehicle_id,
        event_type="fleet.vehicle.created.v1",
        actor_type=auth.actor_type,
        actor_id=auth.actor_id,
        request_id=request_id,
        correlation_id=correlation_id,
        occurred_at_utc=now,
        payload_json={"snapshot": vehicle_snapshot},
    )
    await timeline_repo.insert_timeline_event(session, timeline_event)

    # Step 8: Outbox event (Enriched)
    outbox_event = FleetOutbox(
        outbox_id=str(ULID()),
        aggregate_type=AggregateType.VEHICLE,
        aggregate_id=vehicle_id,
        event_name="fleet.vehicle.created.v1",
        event_version=settings.schema_event_version,
        partition_key=vehicle_id,
        payload_json=json.dumps(
            {
                "event_id": event_id,
                "event_name": "fleet.vehicle.created.v1",
                "event_version": settings.schema_event_version,
                "occurred_at_utc": now.isoformat(),
                "aggregate_type": "VEHICLE",
                "aggregate_id": vehicle_id,
                "row_version": 1,
                "request_id": request_id,
                "correlation_id": correlation_id,
                "data": vehicle_snapshot,
            }
        ),
        publish_status=OutboxPublishStatus.PENDING,
        next_attempt_at_utc=now,
        created_at_utc=now,
    )
    await outbox_repo.insert_outbox_event(session, outbox_event)

    # Step 9: Build response
    response = _build_vehicle_detail_response(vehicle, current_spec=current_spec)

    # Step 10: Idempotency record
    idem_record = FleetIdempotencyRecord(
        idempotency_key=idempotency_key,
        endpoint_fingerprint=_VEHICLE_CREATE_FINGERPRINT,
        request_hash=request_hash,
        response_status_code=201,
        response_body_json=response.model_dump(mode="json"),
        resource_type="VEHICLE",
        resource_id=vehicle_id,
        created_at_utc=now,
        expires_at_utc=now + datetime.timedelta(hours=_IDEMPOTENCY_TTL_HOURS),
    )
    await idempotency_repo.insert_record(session, idem_record)
    await session.commit()
    # committed above

    # Step 11: ETag
    etag = generate_master_etag("VEHICLE", vehicle_id, 1)
    spec_etag = generate_spec_etag("VEHICLE", vehicle_id, vehicle.spec_stream_version) if current_spec else None
    return response, etag, 201, spec_etag


# === LIST ===


async def list_vehicles(
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
    """List vehicles with filters, sort, pagination.

    Section 7.3 default visibility:
    - ACTIVE only by default
    - include_inactive=true → also shows INACTIVE
    - include_soft_deleted=true → also shows soft-deleted
    """
    items, total = await vehicle_repo.get_vehicle_list(
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
        items=[_build_vehicle_list_response(v) for v in items],
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
    )


# === DETAIL ===


async def get_vehicle_detail(session: AsyncSession, vehicle_id: str) -> tuple[VehicleDetailResponse, str]:
    """Get vehicle detail with current spec summary.

    Returns (response, etag).
    """
    vehicle = await vehicle_repo.get_vehicle_by_id(session, vehicle_id, include_soft_deleted=True)
    if not vehicle:
        raise VehicleNotFoundError(vehicle_id)

    current_spec = await vehicle_repo.get_current_vehicle_spec(session, vehicle_id)
    response = _build_vehicle_detail_response(vehicle, current_spec)
    etag = generate_master_etag("VEHICLE", vehicle_id, vehicle.row_version)
    return response, etag


# === PATCH ===


async def patch_vehicle(
    session: AsyncSession,
    vehicle_id: str,
    body: VehiclePatchRequest,
    auth: AuthContext,
    *,
    if_match: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
) -> tuple[VehicleDetailResponse, str]:
    """PATCH vehicle with optimistic locking (master ETag).

    Returns (response, new_etag).
    """
    if not if_match:
        raise EtagRequiredError("master")

    # Parse expected row_version from ETag
    from fleet_service.domain.etag import parse_master_etag

    parsed = parse_master_etag(if_match)
    if not parsed:
        raise EtagMismatchError()
    _, _, expected_version = parsed

    # Lock row
    vehicle = await vehicle_repo.get_vehicle_for_update(session, vehicle_id)
    if not vehicle:
        raise VehicleNotFoundError(vehicle_id)

    # ETag check
    if vehicle.row_version != expected_version:
        raise EtagMismatchError()

    # Guard: cannot PATCH soft-deleted
    if vehicle.soft_deleted_at_utc is not None:
        raise VehicleSoftDeletedError()

    from fleet_service.services.audit_helpers import _write_fleet_audit, serialize_vehicle_admin

    old_snapshot = serialize_vehicle_admin(vehicle)

    now = _utc_now()
    changes: dict[str, Any] = {}

    # Apply changes
    if body.plate is not None:
        new_normalized = normalize_plate(body.plate)
        if not await vehicle_repo.check_plate_uniqueness(session, new_normalized, exclude_vehicle_id=vehicle_id):
            raise VehiclePlateAlreadyExistsError()
        vehicle.plate_raw_current = body.plate
        vehicle.normalized_plate_current = new_normalized
        changes["plate"] = body.plate

    if body.brand is not None:
        vehicle.brand = body.brand
        changes["brand"] = body.brand
    if body.model is not None:
        vehicle.model = body.model
        changes["model"] = body.model
    if body.model_year is not None:
        vehicle.model_year = body.model_year
        changes["model_year"] = body.model_year
    if body.ownership_type is not None:
        vehicle.ownership_type = body.ownership_type
        changes["ownership_type"] = body.ownership_type
    if body.notes is not None:
        vehicle.notes = body.notes
        changes["notes"] = body.notes

    # Increment row_version
    vehicle.row_version += 1
    vehicle.updated_at_utc = now
    vehicle.updated_by_actor_type = auth.actor_type
    vehicle.updated_by_actor_id = auth.actor_id

    try:
        await vehicle_repo.update_vehicle(session, vehicle)
    except IntegrityError as exc:
        raise map_integrity_error(exc, "VEHICLE") from exc

    # Timeline
    event_id = str(ULID())
    await timeline_repo.insert_timeline_event(
        session,
        FleetAssetTimelineEvent(
            event_id=event_id,
            aggregate_type=AggregateType.VEHICLE,
            aggregate_id=vehicle_id,
            event_type="fleet.vehicle.updated.v1",
            actor_type=auth.actor_type,
            actor_id=auth.actor_id,
            request_id=request_id,
            correlation_id=correlation_id,
            occurred_at_utc=now,
            payload_json={"changes": changes, "row_version": vehicle.row_version},
        ),
    )

    # High-fidelity audit
    await _write_fleet_audit(
        session,
        aggregate_type=AggregateType.VEHICLE,
        aggregate_id=vehicle_id,
        action_type="UPDATE",
        actor_id=auth.actor_id,
        actor_role=auth.actor_type,
        old_snapshot=old_snapshot,
        new_snapshot=serialize_vehicle_admin(vehicle),
        changed_fields=changes,
        reason=body.notes or f"Fields changed: {', '.join(changes.keys())}",
        request_id=request_id,
    )

    await outbox_repo.insert_outbox_event(
        session,
        FleetOutbox(
            outbox_id=str(ULID()),
            aggregate_type=AggregateType.VEHICLE,
            aggregate_id=vehicle_id,
            event_name="fleet.vehicle.updated.v1",
            event_version=settings.schema_event_version,
            partition_key=vehicle_id,
            payload_json=json.dumps(
                {
                    "event_id": event_id,
                    "event_name": "fleet.vehicle.updated.v1",
                    "event_version": settings.schema_event_version,
                    "occurred_at_utc": now.isoformat(),
                    "aggregate_type": "VEHICLE",
                    "aggregate_id": vehicle_id,
                    "row_version": vehicle.row_version,
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

    current_spec = await vehicle_repo.get_current_vehicle_spec(session, vehicle_id)
    response = _build_vehicle_detail_response(vehicle, current_spec)
    etag = generate_master_etag("VEHICLE", vehicle_id, vehicle.row_version)
    return response, etag


# === LIFECYCLE: DEACTIVATE / REACTIVATE / SOFT-DELETE ===


async def deactivate_vehicle(
    session: AsyncSession,
    vehicle_id: str,
    reason: str,
    auth: AuthContext,
    *,
    if_match: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
) -> tuple[VehicleDetailResponse, str]:
    """ACTIVE → INACTIVE."""
    return await _lifecycle_transition(
        session,
        vehicle_id,
        reason,
        auth,
        target_status=MasterStatus.INACTIVE,
        valid_from={MasterStatus.ACTIVE},
        event_name="fleet.vehicle.deactivated.v1",
        if_match=if_match,
        request_id=request_id,
        correlation_id=correlation_id,
    )


async def reactivate_vehicle(
    session: AsyncSession,
    vehicle_id: str,
    reason: str,
    auth: AuthContext,
    *,
    if_match: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
) -> tuple[VehicleDetailResponse, str]:
    """INACTIVE → ACTIVE."""
    return await _lifecycle_transition(
        session,
        vehicle_id,
        reason,
        auth,
        target_status=MasterStatus.ACTIVE,
        valid_from={MasterStatus.INACTIVE},
        event_name="fleet.vehicle.reactivated.v1",
        if_match=if_match,
        request_id=request_id,
        correlation_id=correlation_id,
    )


async def soft_delete_vehicle(
    session: AsyncSession,
    vehicle_id: str,
    reason: str,
    auth: AuthContext,
    *,
    if_match: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
) -> tuple[VehicleDetailResponse, str]:
    """Set soft_deleted_at_utc fields."""
    if not if_match:
        raise EtagRequiredError("master")

    from fleet_service.domain.etag import parse_master_etag

    parsed = parse_master_etag(if_match)
    if not parsed:
        raise EtagMismatchError()
    _, _, expected_version = parsed

    vehicle = await vehicle_repo.get_vehicle_for_update(session, vehicle_id)
    if not vehicle:
        raise VehicleNotFoundError(vehicle_id)
    if vehicle.row_version != expected_version:
        raise EtagMismatchError()
    if vehicle.soft_deleted_at_utc is not None:
        raise AssetAlreadyInTargetStateError("SOFT_DELETED")

    now = _utc_now()
    vehicle.soft_deleted_at_utc = now
    vehicle.soft_deleted_by_actor_type = auth.actor_type
    vehicle.soft_deleted_by_actor_id = auth.actor_id
    vehicle.soft_delete_reason = reason
    vehicle.row_version += 1
    vehicle.updated_at_utc = now
    vehicle.updated_by_actor_type = auth.actor_type
    vehicle.updated_by_actor_id = auth.actor_id

    await vehicle_repo.update_vehicle(session, vehicle)

    event_id = str(ULID())
    await timeline_repo.insert_timeline_event(
        session,
        FleetAssetTimelineEvent(
            event_id=event_id,
            aggregate_type=AggregateType.VEHICLE,
            aggregate_id=vehicle_id,
            event_type="fleet.vehicle.soft_deleted.v1",
            actor_type=auth.actor_type,
            actor_id=auth.actor_id,
            request_id=request_id,
            correlation_id=correlation_id,
            occurred_at_utc=now,
            payload_json={"reason": reason, "row_version": vehicle.row_version},
        ),
    )

    await outbox_repo.insert_outbox_event(
        session,
        FleetOutbox(
            outbox_id=str(ULID()),
            aggregate_type=AggregateType.VEHICLE,
            aggregate_id=vehicle_id,
            event_name="fleet.vehicle.soft_deleted.v1",
            event_version=settings.schema_event_version,
            partition_key=vehicle_id,
            payload_json=json.dumps(
                {
                    "event_id": event_id,
                    "event_name": "fleet.vehicle.soft_deleted.v1",
                    "event_version": settings.schema_event_version,
                    "occurred_at_utc": now.isoformat(),
                    "aggregate_type": "VEHICLE",
                    "aggregate_id": vehicle_id,
                    "row_version": vehicle.row_version,
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

    current_spec = await vehicle_repo.get_current_vehicle_spec(session, vehicle_id)
    response = _build_vehicle_detail_response(vehicle, current_spec)
    etag = generate_master_etag("VEHICLE", vehicle_id, vehicle.row_version)
    return response, etag


# === HARD DELETE (4-stage — Section 7.5) ===


async def hard_delete_vehicle(
    session: AsyncSession,
    vehicle_id: str,
    reason: str,
    auth: AuthContext,
    *,
    if_match: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
    trip_reference_checker: Any = None,
) -> dict[str, Any]:
    """Hard-delete with 4-stage pipeline (Section 7.5).

    Stage 0: Auth (already done by router guard — SUPER_ADMIN required)
    Stage 1: Non-locking SELECT → 404/412/422 (no Trip call yet)
    Stage 2: Trip reference-check → 503/409
    Stage 3: FOR UPDATE → re-verify → audit → dead-letter → DELETE → commit
    """
    now = _utc_now()

    # --- Stage 1: Non-locking pre-check ---
    if not if_match:
        raise EtagRequiredError("master")

    from fleet_service.domain.etag import parse_master_etag

    parsed = parse_master_etag(if_match)
    if not parsed:
        raise EtagMismatchError()
    _, _, expected_version = parsed

    vehicle = await vehicle_repo.get_vehicle_by_id(session, vehicle_id, include_soft_deleted=True)
    if not vehicle:
        await _audit_hard_delete(
            session,
            vehicle_id,
            None,
            auth,
            now,
            DeleteResult.REJECTED_NOT_FOUND,
            "Vehicle not found",
            request_id,
        )
        raise VehicleNotFoundError(vehicle_id)

    if vehicle.row_version != expected_version:
        await _audit_hard_delete(
            session,
            vehicle_id,
            vehicle,
            auth,
            now,
            DeleteResult.REJECTED_ETAG_MISMATCH,
            "ETag mismatch",
            request_id,
        )
        raise EtagMismatchError()

    if vehicle.soft_deleted_at_utc is None:
        await _audit_hard_delete(
            session,
            vehicle_id,
            vehicle,
            auth,
            now,
            DeleteResult.REJECTED_NOT_SOFT_DELETED,
            "Vehicle must be soft-deleted before hard-delete",
            request_id,
        )
        raise InvalidStatusTransitionError("Vehicle must be soft-deleted before hard-delete")

    # --- Stage 2: Trip reference-check ---
    ref_check_status = ReferenceCheckStatus.NOT_ATTEMPTED
    ref_check_json = None
    if trip_reference_checker:
        try:
            ref_result = await trip_reference_checker(vehicle_id, "VEHICLE")
            ref_check_status = ReferenceCheckStatus.SUCCEEDED
            ref_check_json = ref_result
            if ref_result.get("has_references", False):
                await _audit_hard_delete(
                    session,
                    vehicle_id,
                    vehicle,
                    auth,
                    now,
                    DeleteResult.REJECTED_REFERENCED,
                    "Vehicle is referenced by trips",
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
                vehicle_id,
                vehicle,
                auth,
                now,
                DeleteResult.REJECTED_DEPENDENCY_UNAVAILABLE,
                "Trip service unavailable",
                request_id,
                ref_check_status,
            )
            raise DependencyUnavailableError("trip-service")

    # --- Stage 3: FOR UPDATE → re-verify → delete ---
    locked_vehicle = await vehicle_repo.get_vehicle_for_update(session, vehicle_id)
    if not locked_vehicle:
        raise VehicleNotFoundError(vehicle_id)
    if locked_vehicle.row_version != expected_version:
        raise EtagMismatchError()
    # Re-verify soft_deleted_at_utc IS NOT NULL (race safety — plan Step 11)
    if locked_vehicle.soft_deleted_at_utc is None:
        raise InvalidStatusTransitionError("Vehicle must be soft-deleted before hard-delete")

    # Dead-letter pending outbox events (plan Step 13)
    await outbox_repo.dead_letter_by_aggregate(session, AggregateType.VEHICLE, vehicle_id)

    # Snapshot for audit
    snapshot = _build_vehicle_snapshot(locked_vehicle)

    # Delete spec versions first (plan Step 14), then master (plan Step 15)
    await vehicle_repo.delete_vehicle_spec_versions(session, vehicle_id)
    await vehicle_repo.hard_delete_vehicle(session, locked_vehicle)

    # Audit: SUCCEEDED
    audit_id = str(ULID())
    await delete_audit_repo.insert_delete_audit(
        session,
        FleetAssetDeleteAudit(
            delete_audit_id=audit_id,
            aggregate_type=AggregateType.VEHICLE,
            aggregate_id=vehicle_id,
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

    # Timeline (tombstone)
    event_id = str(ULID())
    await timeline_repo.insert_timeline_event(
        session,
        FleetAssetTimelineEvent(
            event_id=event_id,
            aggregate_type=AggregateType.VEHICLE,
            aggregate_id=vehicle_id,
            event_type="fleet.vehicle.hard_deleted.v1",
            actor_type=auth.actor_type,
            actor_id=auth.actor_id,
            request_id=request_id,
            correlation_id=correlation_id,
            occurred_at_utc=now,
            payload_json={"reason": reason, "snapshot_json": snapshot},
        ),
    )

    # Outbox (tombstone — published immediately by dead-lettering others first)
    await outbox_repo.insert_outbox_event(
        session,
        FleetOutbox(
            outbox_id=str(ULID()),
            aggregate_type=AggregateType.VEHICLE,
            aggregate_id=vehicle_id,
            event_name="fleet.vehicle.hard_deleted.v1",
            event_version=settings.schema_event_version,
            partition_key=vehicle_id,
            payload_json=json.dumps(
                {
                    "event_id": event_id,
                    "event_name": "fleet.vehicle.hard_deleted.v1",
                    "event_version": settings.schema_event_version,
                    "occurred_at_utc": now.isoformat(),
                    "aggregate_type": "VEHICLE",
                    "aggregate_id": vehicle_id,
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

    return {"deleted": True, "aggregate_type": "VEHICLE", "aggregate_id": vehicle_id, "delete_audit_id": audit_id}


# === TIMELINE ===


async def get_vehicle_timeline(
    session: AsyncSession,
    vehicle_id: str,
    *,
    page: int = 1,
    per_page: int = 50,
) -> list[dict[str, Any]]:
    """Get vehicle timeline events.

    Section 7.5 post-hard-delete behavior:
    - If vehicle exists (including soft-deleted): return timeline
    - If vehicle hard-deleted: return timeline if rows exist, else 404
    - Timeline events survive hard-delete (no FK cascade).
    """
    events = await timeline_repo.get_timeline_by_aggregate(
        session, AggregateType.VEHICLE, vehicle_id, page=page, per_page=per_page
    )
    # If no events and vehicle doesn't exist → 404
    if not events:
        vehicle = await vehicle_repo.get_vehicle_by_id(session, vehicle_id, include_soft_deleted=True)
        if not vehicle:
            raise VehicleNotFoundError(vehicle_id)

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


# === INTERNAL HELPERS ===


async def _lifecycle_transition(
    session: AsyncSession,
    vehicle_id: str,
    reason: str,
    auth: AuthContext,
    *,
    target_status: str,
    valid_from: set[str],
    event_name: str,
    if_match: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
) -> tuple[VehicleDetailResponse, str]:
    """Generic lifecycle transition (deactivate/reactivate)."""
    if not if_match:
        raise EtagRequiredError("master")

    from fleet_service.domain.etag import parse_master_etag

    parsed = parse_master_etag(if_match)
    if not parsed:
        raise EtagMismatchError()
    _, _, expected_version = parsed

    vehicle = await vehicle_repo.get_vehicle_for_update(session, vehicle_id)
    if not vehicle:
        raise VehicleNotFoundError(vehicle_id)
    if vehicle.row_version != expected_version:
        raise EtagMismatchError()
    if vehicle.soft_deleted_at_utc is not None:
        raise VehicleSoftDeletedError()
    if vehicle.status == target_status:
        raise AssetAlreadyInTargetStateError(target_status)
    if vehicle.status not in valid_from:
        raise InvalidStatusTransitionError(f"Cannot transition from {vehicle.status} to {target_status}")

    now = _utc_now()
    vehicle.status = target_status
    vehicle.row_version += 1
    vehicle.updated_at_utc = now
    vehicle.updated_by_actor_type = auth.actor_type
    vehicle.updated_by_actor_id = auth.actor_id

    await vehicle_repo.update_vehicle(session, vehicle)

    event_id = str(ULID())
    await timeline_repo.insert_timeline_event(
        session,
        FleetAssetTimelineEvent(
            event_id=event_id,
            aggregate_type=AggregateType.VEHICLE,
            aggregate_id=vehicle_id,
            event_type=event_name,
            actor_type=auth.actor_type,
            actor_id=auth.actor_id,
            request_id=request_id,
            correlation_id=correlation_id,
            occurred_at_utc=now,
            payload_json={"reason": reason, "row_version": vehicle.row_version, "status": target_status},
        ),
    )

    await outbox_repo.insert_outbox_event(
        session,
        FleetOutbox(
            outbox_id=str(ULID()),
            aggregate_type=AggregateType.VEHICLE,
            aggregate_id=vehicle_id,
            event_name=event_name,
            event_version=settings.schema_event_version,
            partition_key=vehicle_id,
            payload_json=json.dumps(
                {
                    "event_id": event_id,
                    "event_name": event_name,
                    "event_version": settings.schema_event_version,
                    "occurred_at_utc": now.isoformat(),
                    "aggregate_type": "VEHICLE",
                    "aggregate_id": vehicle_id,
                    "row_version": vehicle.row_version,
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

    current_spec = await vehicle_repo.get_current_vehicle_spec(session, vehicle_id)
    response = _build_vehicle_detail_response(vehicle, current_spec)
    etag = generate_master_etag("VEHICLE", vehicle_id, vehicle.row_version)
    return response, etag


async def _audit_hard_delete(
    session: AsyncSession,
    vehicle_id: str,
    vehicle: FleetVehicle | None,
    auth: AuthContext,
    now: datetime.datetime,
    result: str,
    reason: str,
    request_id: str | None = None,
    ref_check_status: str = ReferenceCheckStatus.NOT_ATTEMPTED,
    ref_check_json: dict[str, Any] | None = None,
) -> None:
    """Write a delete audit row for any rejection/success path."""
    snapshot = _build_vehicle_snapshot(vehicle) if vehicle else {}
    await delete_audit_repo.insert_delete_audit(
        session,
        FleetAssetDeleteAudit(
            delete_audit_id=str(ULID()),
            aggregate_type=AggregateType.VEHICLE,
            aggregate_id=vehicle_id,
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


def _build_vehicle_detail_response(vehicle: FleetVehicle, current_spec: Any | None) -> VehicleDetailResponse:
    """Build a VehicleDetailResponse from ORM model."""
    is_selectable = vehicle.soft_deleted_at_utc is None and vehicle.status == MasterStatus.ACTIVE
    spec_summary = None
    if current_spec:
        spec_summary = CurrentSpecSummary(
            version_no=current_spec.version_no,
            fuel_type=current_spec.fuel_type,
            powertrain_type=current_spec.powertrain_type,
            emission_class=current_spec.emission_class,
            curb_weight_kg=current_spec.curb_weight_kg,
            gvwr_kg=current_spec.gvwr_kg,
            effective_from_utc=current_spec.effective_from_utc,
        )
    return VehicleDetailResponse(
        vehicle_id=vehicle.vehicle_id,
        asset_code=vehicle.asset_code,
        plate_raw_current=vehicle.plate_raw_current,
        normalized_plate_current=vehicle.normalized_plate_current,
        brand=vehicle.brand,
        model=vehicle.model,
        model_year=vehicle.model_year,
        ownership_type=vehicle.ownership_type,
        status=vehicle.status,
        lifecycle_state=vehicle.lifecycle_state,
        notes=vehicle.notes,
        row_version=vehicle.row_version,
        spec_stream_version=vehicle.spec_stream_version,
        is_selectable=is_selectable,
        current_spec_summary=spec_summary,
        created_at_utc=vehicle.created_at_utc,
        created_by_actor_type=vehicle.created_by_actor_type,
        created_by_actor_id=vehicle.created_by_actor_id,
        updated_at_utc=vehicle.updated_at_utc,
        updated_by_actor_type=vehicle.updated_by_actor_type,
        updated_by_actor_id=vehicle.updated_by_actor_id,
        soft_deleted_at_utc=vehicle.soft_deleted_at_utc,
        soft_deleted_by_actor_type=vehicle.soft_deleted_by_actor_type,
        soft_deleted_by_actor_id=vehicle.soft_deleted_by_actor_id,
        soft_delete_reason=vehicle.soft_delete_reason,
    )


def _build_vehicle_list_response(vehicle: FleetVehicle) -> VehicleListItemResponse:
    """Build a VehicleListItemResponse from ORM model."""
    is_selectable = vehicle.soft_deleted_at_utc is None and vehicle.status == MasterStatus.ACTIVE
    return VehicleListItemResponse(
        vehicle_id=vehicle.vehicle_id,
        asset_code=vehicle.asset_code,
        plate_raw_current=vehicle.plate_raw_current,
        normalized_plate_current=vehicle.normalized_plate_current,
        brand=vehicle.brand,
        model=vehicle.model,
        model_year=vehicle.model_year,
        ownership_type=vehicle.ownership_type,
        status=vehicle.status,
        lifecycle_state=vehicle.lifecycle_state,
        row_version=vehicle.row_version,
        spec_stream_version=vehicle.spec_stream_version,
        is_selectable=is_selectable,
        created_at_utc=vehicle.created_at_utc,
        updated_at_utc=vehicle.updated_at_utc,
    )


def _build_vehicle_snapshot(vehicle: FleetVehicle) -> dict[str, Any]:
    """Build a snapshot dict for delete audit."""
    return {
        "vehicle_id": vehicle.vehicle_id,
        "asset_code": vehicle.asset_code,
        "plate_raw_current": vehicle.plate_raw_current,
        "normalized_plate_current": vehicle.normalized_plate_current,
        "brand": vehicle.brand,
        "model": vehicle.model,
        "model_year": vehicle.model_year,
        "ownership_type": vehicle.ownership_type,
        "status": vehicle.status,
        "row_version": vehicle.row_version,
        "spec_stream_version": vehicle.spec_stream_version,
        "created_at_utc": vehicle.created_at_utc.isoformat() if vehicle.created_at_utc else None,
        "updated_at_utc": vehicle.updated_at_utc.isoformat() if vehicle.updated_at_utc else None,
    }
