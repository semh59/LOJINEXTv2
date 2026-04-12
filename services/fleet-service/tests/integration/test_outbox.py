import json
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from fleet_service.models import FleetOutbox
from tests.conftest import ADMIN_HEADERS


@pytest.mark.asyncio
async def test_outbox_event_emission_on_create(client: AsyncClient, test_session):
    # 1. Create a vehicle
    headers = {**ADMIN_HEADERS, "Idempotency-Key": "outbox-test-01"}
    resp = await client.post(
        "/api/v1/vehicles",
        json={"asset_code": "V-OUT-01", "plate": "34 OUT 01", "ownership_type": "OWNED"},
        headers=headers,
    )
    assert resp.status_code == 201
    vehicle_id = resp.json()["vehicle_id"]

    # 2. Verify Outbox record exists in DB
    # We use test_session which is an AsyncSession for direct DB access
    stmt = select(FleetOutbox).where(FleetOutbox.aggregate_id == vehicle_id)
    result = await test_session.execute(stmt)
    outbox_events = result.scalars().all()

    assert len(outbox_events) == 1
    event = outbox_events[0]
    assert event.event_name == "fleet.vehicle.created.v1"
    assert event.publish_status == "PENDING"
    assert json.loads(event.payload_json)["aggregate_id"] == vehicle_id


@pytest.mark.asyncio
async def test_outbox_dead_lettering_on_hard_delete(client: AsyncClient, test_session, super_admin_headers):
    # 1. Create then soft-delete
    headers = {**ADMIN_HEADERS, "Idempotency-Key": "outbox-test-02"}
    resp = await client.post(
        "/api/v1/vehicles",
        json={"asset_code": "V-OUT-02", "plate": "34 OUT 02", "ownership_type": "OWNED"},
        headers=headers,
    )
    vehicle_id = resp.json()["vehicle_id"]
    etag = resp.headers["ETag"]

    # Soft delete (Status PENDING outbox)
    resp = await client.post(
        f"/api/v1/vehicles/{vehicle_id}/soft-delete",
        json={"reason": "Delete Test"},
        headers={**ADMIN_HEADERS, "If-Match": etag},
    )
    soft_etag = resp.headers["ETag"]

    # 2. Hard delete should DEAD_LETTER previous events for this aggregate
    resp = await client.post(
        f"/api/v1/vehicles/{vehicle_id}/hard-delete",
        json={"reason": "Audit cleanup"},
        headers={**super_admin_headers, "If-Match": soft_etag},
    )
    assert resp.status_code == 200

    # 3. Verify outbox states
    stmt = select(FleetOutbox).where(FleetOutbox.aggregate_id == vehicle_id)
    result = await test_session.execute(stmt)
    events = result.scalars().all()

    # Should have 'created', 'soft_deleted', and 'hard_deleted'
    dead_lettered = [e for e in events if e.publish_status == "DEAD_LETTER"]
    pending = [e for e in events if e.publish_status == "PENDING"]

    assert len(dead_lettered) >= 2  # created + soft_deleted
    assert len(pending) == 1  # hard_deleted (tombstone) is the only active one
    assert pending[0].event_name == "fleet.vehicle.hard_deleted.v1"
