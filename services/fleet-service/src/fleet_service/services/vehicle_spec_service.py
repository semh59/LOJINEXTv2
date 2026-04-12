"""Vehicle spec version service â€” business logic for 3 spec endpoints.

Orchestrates repositories, writes timeline + outbox events within the same transaction.
"""

from __future__ import annotations

import datetime
import json
import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from fleet_service.auth import AuthContext
from fleet_service.config import settings
from fleet_service.constraint_error_mapper import map_integrity_error
from fleet_service.domain.enums import AggregateType
from platform_common import OutboxPublishStatus
from fleet_service.domain.etag import generate_spec_etag, parse_spec_etag
from fleet_service.errors import (
    AssetInactiveOrDeletedError,
    EtagRequiredError,
    SpecEtagMismatchError,
    SpecNotFoundForInstantError,
    SpecNotInitializedError,
    SpecVersionOverlapError,
    VehicleNotFoundError,
)
from fleet_service.models import (
    FleetAssetTimelineEvent,
    FleetOutbox,
    FleetVehicleSpecVersion,
)
from fleet_service.repositories import (
    outbox_repo,
    timeline_repo,
    vehicle_repo,
    vehicle_spec_repo,
)
from fleet_service.schemas.requests import VehicleSpecVersionRequest
from fleet_service.schemas.responses import VehicleSpecResponse
from fleet_service.timestamps import to_utc_aware, utc_now_aware

logger = logging.getLogger("fleet_service.vehicle_spec_service")


def _utc_now() -> datetime.datetime:
    """Return the current naive UTC timestamp for the Fleet schema."""
    return utc_now_aware()


# === CREATE SPEC VERSION (13-step) ===


async def create_vehicle_spec_version(
    session: AsyncSession,
    vehicle_id: str,
    body: VehicleSpecVersionRequest,
    auth: AuthContext,
    *,
    if_match: str | None = None,
    request_id: str | None = None,
    correlation_id: str | None = None,
) -> tuple[VehicleSpecResponse, str, int]:
    """Create a new vehicle spec version (13-step sequence).

    Returns (response, spec_etag, status_code).
    """
    # Step 1: Require If-Match (spec ETag)
    if not if_match:
        raise EtagRequiredError("spec")

    # Step 2: Parse spec ETag
    parsed = parse_spec_etag(if_match)
    if not parsed:
        raise SpecEtagMismatchError()
    _, _, expected_spec_version = parsed

    # Step 3: Lock vehicle row (FOR UPDATE)
    vehicle = await vehicle_repo.get_vehicle_for_update(session, vehicle_id)
    if not vehicle:
        raise VehicleNotFoundError(vehicle_id)

    # Step 4: Guard â€” cannot add spec to inactive or soft-deleted vehicle
    if vehicle.soft_deleted_at_utc is not None or vehicle.status != "ACTIVE":
        raise AssetInactiveOrDeletedError()

    # Step 5: Compare spec_stream_version
    if vehicle.spec_stream_version != expected_spec_version:
        raise SpecEtagMismatchError()

    now = _utc_now()

    # Step 6: Default effective_from_utc
    effective_from = to_utc_aware(body.effective_from_utc) if body.effective_from_utc else now

    # Step 7: Get max version_no â†’ new_version_no
    max_version = await vehicle_spec_repo.get_max_version_no(session, vehicle_id)
    new_version_no = max_version + 1

    # Step 8: Build new spec version entity
    spec_version_id = str(ULID())
    spec = FleetVehicleSpecVersion(
        vehicle_spec_version_id=spec_version_id,
        vehicle_id=vehicle_id,
        version_no=new_version_no,
        effective_from_utc=effective_from,
        effective_to_utc=None,
        is_current=True,
        fuel_type=body.fuel_type,
        powertrain_type=body.powertrain_type,
        engine_power_kw=body.engine_power_kw,
        engine_displacement_l=body.engine_displacement_l,
        emission_class=body.emission_class,
        transmission_type=body.transmission_type,
        gear_count=body.gear_count,
        final_drive_ratio=body.final_drive_ratio,
        axle_config=body.axle_config,
        total_axle_count=body.total_axle_count,
        driven_axle_count=body.driven_axle_count,
        curb_weight_kg=body.curb_weight_kg,
        gvwr_kg=body.gvwr_kg,
        gcwr_kg=body.gcwr_kg,
        payload_capacity_kg=body.payload_capacity_kg,
        tractor_cab_type=body.tractor_cab_type,
        roof_height_class=body.roof_height_class,
        aero_package_level=body.aero_package_level,
        tire_rr_class=body.tire_rr_class,
        tire_type=body.tire_type,
        speed_limiter_kph=body.speed_limiter_kph,
        pto_present=body.pto_present,
        apu_present=body.apu_present,
        idle_reduction_type=body.idle_reduction_type,
        first_registration_date=body.first_registration_date,
        in_service_date=body.in_service_date,
        change_reason=body.change_reason,
        created_at_utc=now,
        created_by_actor_type=auth.actor_type,
        created_by_actor_id=auth.actor_id,
    )

    # Step 9-10: Close current spec and INSERT new row (constraint checks can fail in either step)
    try:
        await vehicle_spec_repo.close_current_spec(session, vehicle_id, effective_from)
        await vehicle_spec_repo.insert_spec_version(session, spec)
    except IntegrityError as exc:
        mapped = map_integrity_error(exc, "VEHICLE")
        if mapped:
            raise mapped from exc
        raise SpecVersionOverlapError() from exc

    # Step 11: Increment spec_stream_version on master
    vehicle.spec_stream_version += 1
    vehicle.updated_at_utc = now
    vehicle.updated_by_actor_type = auth.actor_type
    vehicle.updated_by_actor_id = auth.actor_id
    await vehicle_repo.update_vehicle(session, vehicle)

    # Step 12: Timeline event
    event_id = str(ULID())
    await timeline_repo.insert_timeline_event(
        session,
        FleetAssetTimelineEvent(
            event_id=event_id,
            aggregate_type=AggregateType.VEHICLE,
            aggregate_id=vehicle_id,
            event_type="fleet.vehicle.spec_version_created.v1",
            actor_type=auth.actor_type,
            actor_id=auth.actor_id,
            request_id=request_id,
            correlation_id=correlation_id,
            occurred_at_utc=now,
            payload_json={
                "vehicle_spec_version_id": spec_version_id,
                "version_no": new_version_no,
                "change_reason": body.change_reason,
                "spec_stream_version": vehicle.spec_stream_version,
            },
        ),
    )

    # Step 13: Outbox event
    await outbox_repo.insert_outbox_event(
        session,
        FleetOutbox(
            outbox_id=str(ULID()),
            aggregate_type=AggregateType.VEHICLE,
            aggregate_id=vehicle_id,
            event_name="fleet.vehicle.spec_version_created.v1",
            event_version=settings.schema_event_version,
            partition_key=vehicle_id,
            payload_json=json.dumps(
                {
                    "event_id": event_id,
                    "event_name": "fleet.vehicle.spec_version_created.v1",
                    "occurred_at_utc": now.isoformat(),
                    "aggregate_type": "VEHICLE",
                    "aggregate_id": vehicle_id,
                    "vehicle_spec_version_id": spec_version_id,
                    "version_no": new_version_no,
                    "spec_stream_version": vehicle.spec_stream_version,
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
    etag = generate_spec_etag("VEHICLE", vehicle_id, vehicle.spec_stream_version)
    await session.commit()
    return response, etag, 201


# === GET CURRENT SPEC ===


async def get_current_spec(session: AsyncSession, vehicle_id: str) -> tuple[VehicleSpecResponse, str]:
    """Get the current spec version for a vehicle.

    Returns (response, spec_etag).
    """
    vehicle = await vehicle_repo.get_vehicle_by_id(session, vehicle_id, include_soft_deleted=True)
    if not vehicle:
        raise VehicleNotFoundError(vehicle_id)

    spec = await vehicle_spec_repo.get_current_spec(session, vehicle_id)
    if not spec:
        raise SpecNotInitializedError("VEHICLE")

    response = _build_spec_response(spec)
    etag = generate_spec_etag("VEHICLE", vehicle_id, vehicle.spec_stream_version)
    return response, etag


# === GET SPEC AS-OF ===


async def get_spec_as_of(session: AsyncSession, vehicle_id: str, at: datetime.datetime) -> VehicleSpecResponse:
    """Get the spec version effective at a given timestamp."""
    vehicle = await vehicle_repo.get_vehicle_by_id(session, vehicle_id, include_soft_deleted=True)
    if not vehicle:
        raise VehicleNotFoundError(vehicle_id)

    spec = await vehicle_spec_repo.get_spec_as_of(session, vehicle_id, to_utc_aware(at))
    if not spec:
        raise SpecNotFoundForInstantError(at.isoformat())

    return _build_spec_response(spec)


# === INTERNAL HELPERS ===


def _build_spec_response(spec: FleetVehicleSpecVersion) -> VehicleSpecResponse:
    """Build a VehicleSpecResponse from ORM model."""
    return VehicleSpecResponse(
        vehicle_spec_version_id=spec.vehicle_spec_version_id,
        vehicle_id=spec.vehicle_id,
        version_no=spec.version_no,
        effective_from_utc=spec.effective_from_utc,
        effective_to_utc=spec.effective_to_utc,
        is_current=spec.is_current,
        fuel_type=spec.fuel_type,
        powertrain_type=spec.powertrain_type,
        engine_power_kw=spec.engine_power_kw,
        engine_displacement_l=spec.engine_displacement_l,
        emission_class=spec.emission_class,
        transmission_type=spec.transmission_type,
        gear_count=spec.gear_count,
        final_drive_ratio=spec.final_drive_ratio,
        axle_config=spec.axle_config,
        total_axle_count=spec.total_axle_count,
        driven_axle_count=spec.driven_axle_count,
        curb_weight_kg=spec.curb_weight_kg,
        gvwr_kg=spec.gvwr_kg,
        gcwr_kg=spec.gcwr_kg,
        payload_capacity_kg=spec.payload_capacity_kg,
        tractor_cab_type=spec.tractor_cab_type,
        roof_height_class=spec.roof_height_class,
        aero_package_level=spec.aero_package_level,
        tire_rr_class=spec.tire_rr_class,
        tire_type=spec.tire_type,
        speed_limiter_kph=spec.speed_limiter_kph,
        pto_present=spec.pto_present,
        apu_present=spec.apu_present,
        idle_reduction_type=spec.idle_reduction_type,
        first_registration_date=spec.first_registration_date,
        in_service_date=spec.in_service_date,
        change_reason=spec.change_reason,
        created_at_utc=spec.created_at_utc,
        created_by_actor_type=spec.created_by_actor_type,
        created_by_actor_id=spec.created_by_actor_id,
    )
