import datetime
from unittest.mock import AsyncMock, patch

import pytest

from fleet_service.auth import AuthContext
from fleet_service.domain.enums import MasterStatus
from fleet_service.domain.etag import generate_master_etag
from fleet_service.errors import (
    AssetAlreadyInTargetStateError,
    EtagMismatchError,
    InvalidStatusTransitionError,
    VehicleSoftDeletedError,
)
from fleet_service.models import FleetVehicle
from fleet_service.services.vehicle_service import _lifecycle_transition


@pytest.fixture
def auth_context():
    return AuthContext(role="SUPER_ADMIN", actor_id="test-admin")


@pytest.fixture
def active_vehicle():
    return FleetVehicle(
        vehicle_id="01H1234567890ABCDEFGHJKMNP",
        asset_code="V-UNIT-001",
        plate_raw_current="34 UNIT 01",
        normalized_plate_current="34UNIT01",
        brand="Mercedes",
        model="Actros",
        model_year=2024,
        ownership_type="OWNED",
        status=MasterStatus.ACTIVE,
        row_version=1,
        spec_stream_version=0,
        created_at_utc=datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
        created_by_actor_type="SUPER_ADMIN",
        created_by_actor_id="test-admin",
        updated_at_utc=datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
        updated_by_actor_type="SUPER_ADMIN",
        updated_by_actor_id="test-admin",
        soft_deleted_at_utc=None,
    )


@pytest.mark.asyncio
async def test_transition_active_to_inactive_success(active_vehicle, auth_context):
    session = AsyncMock()
    etag = generate_master_etag("VEHICLE", active_vehicle.vehicle_id, 1)

    with (
        patch(
            "fleet_service.services.vehicle_service.vehicle_repo.get_vehicle_for_update",
            AsyncMock(return_value=active_vehicle),
        ),
        patch("fleet_service.services.vehicle_service.vehicle_repo.update_vehicle", AsyncMock()),
        patch("fleet_service.services.vehicle_service.timeline_repo.insert_timeline_event", AsyncMock()),
        patch("fleet_service.services.vehicle_service.outbox_repo.insert_outbox_event", AsyncMock()),
        patch(
            "fleet_service.services.vehicle_service.vehicle_repo.get_current_vehicle_spec", AsyncMock(return_value=None)
        ),
    ):
        resp, new_etag = await _lifecycle_transition(
            session,
            active_vehicle.vehicle_id,
            "test reason",
            auth_context,
            target_status=MasterStatus.INACTIVE,
            valid_from={MasterStatus.ACTIVE},
            event_name="fleet.vehicle.deactivated.v1",
            if_match=etag,
        )

        assert active_vehicle.status == MasterStatus.INACTIVE
        assert active_vehicle.row_version == 2
        assert new_etag.startswith('W/"vehicle-')


@pytest.mark.asyncio
async def test_transition_already_in_target_state(active_vehicle, auth_context):
    session = AsyncMock()
    etag = generate_master_etag("VEHICLE", active_vehicle.vehicle_id, 1)

    with patch(
        "fleet_service.services.vehicle_service.vehicle_repo.get_vehicle_for_update",
        AsyncMock(return_value=active_vehicle),
    ):
        with pytest.raises(AssetAlreadyInTargetStateError):
            await _lifecycle_transition(
                session,
                active_vehicle.vehicle_id,
                "reason",
                auth_context,
                target_status=MasterStatus.ACTIVE,
                valid_from={MasterStatus.INACTIVE},
                event_name="test.event",
                if_match=etag,
            )


@pytest.mark.asyncio
async def test_transition_invalid_source_state(active_vehicle, auth_context):
    session = AsyncMock()
    # active_vehicle starts as ACTIVE
    # We try to transition it as if it was INACTIVE
    etag = generate_master_etag("VEHICLE", active_vehicle.vehicle_id, 1)

    with patch(
        "fleet_service.services.vehicle_service.vehicle_repo.get_vehicle_for_update",
        AsyncMock(return_value=active_vehicle),
    ):
        with pytest.raises(InvalidStatusTransitionError):
            await _lifecycle_transition(
                session,
                active_vehicle.vehicle_id,
                "reason",
                auth_context,
                target_status=MasterStatus.INACTIVE,
                valid_from={MasterStatus.INACTIVE},  # It must be INACTIVE first
                event_name="test.event",
                if_match=etag,
            )


@pytest.mark.asyncio
async def test_transition_soft_deleted_forbidden(active_vehicle, auth_context):
    session = AsyncMock()
    active_vehicle.soft_deleted_at_utc = datetime.datetime.now()
    etag = generate_master_etag("VEHICLE", active_vehicle.vehicle_id, 1)

    with patch(
        "fleet_service.services.vehicle_service.vehicle_repo.get_vehicle_for_update",
        AsyncMock(return_value=active_vehicle),
    ):
        with pytest.raises(VehicleSoftDeletedError):
            await _lifecycle_transition(
                session,
                active_vehicle.vehicle_id,
                "reason",
                auth_context,
                target_status=MasterStatus.INACTIVE,
                valid_from={MasterStatus.ACTIVE},
                event_name="test.event",
                if_match=etag,
            )


@pytest.mark.asyncio
async def test_transition_etag_mismatch(active_vehicle, auth_context):
    session = AsyncMock()
    wrong_etag = generate_master_etag("VEHICLE", active_vehicle.vehicle_id, 999)

    with patch(
        "fleet_service.services.vehicle_service.vehicle_repo.get_vehicle_for_update",
        AsyncMock(return_value=active_vehicle),
    ):
        with pytest.raises(EtagMismatchError):
            await _lifecycle_transition(
                session,
                active_vehicle.vehicle_id,
                "reason",
                auth_context,
                target_status=MasterStatus.INACTIVE,
                valid_from={MasterStatus.ACTIVE},
                event_name="test.event",
                if_match=wrong_etag,
            )
