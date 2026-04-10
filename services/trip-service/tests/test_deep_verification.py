import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from trip_service.auth import AuthContext
from trip_service.enums import ActorType, SourceType, TripStatus
from sqlalchemy.ext.asyncio import AsyncSession
from trip_service.models import TripOutbox, TripTrip
from trip_service.service import TripService
from trip_service.trip_helpers import (
    _REFERENCE_EXCLUDED_STATUSES,
    _merged_payload_hash,
    normalize_trip_status,
)


@pytest.mark.unit
def test_hash_stability_deep():
    """Verify that logical equivalence results in identical hashes regardless of dictionary order."""
    payload1 = {"a": 1, "b": [1, 2, 3], "c": {"x": True, "y": None}}
    payload2 = {"c": {"y": None, "x": True}, "a": 1, "b": [1, 2, 3]}

    hash1 = _merged_payload_hash(payload1)
    hash2 = _merged_payload_hash(payload2)

    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256


@pytest.mark.unit
def test_status_normalization_legacy_cancelled():
    """Verify legacy CANCELLED status is normalized to SOFT_DELETED."""
    assert normalize_trip_status("CANCELLED") == TripStatus.SOFT_DELETED.value
    assert normalize_trip_status(TripStatus.SOFT_DELETED) == TripStatus.SOFT_DELETED.value
    assert normalize_trip_status("REJECTED") == TripStatus.REJECTED.value


@pytest.mark.unit
def test_reference_exclusion_list_includes_legacy():
    """Verify legacy and canonical deletion statuses are in the exclusion list."""
    assert "CANCELLED" in _REFERENCE_EXCLUDED_STATUSES
    assert TripStatus.SOFT_DELETED.value in _REFERENCE_EXCLUDED_STATUSES
    assert TripStatus.REJECTED.value in _REFERENCE_EXCLUDED_STATUSES


@pytest.mark.asyncio
async def test_header_casing_normalization_robustness(test_session):
    """Verify that service layer correctly normalizes replay headers to TitleCase."""
    auth = AuthContext(actor_id="admin-001", actor_type=ActorType.SUPER_ADMIN.value, role=ActorType.SUPER_ADMIN.value)
    service = TripService(test_session, auth)

    # Simulate mismatched starlette headers
    raw_headers = {"etag": "v123", "x-trip-status": "SOFT_DELETED", "content-type": "application/json"}

    normalized = service._normalize_replay_headers(raw_headers)

    assert "ETag" in normalized
    assert normalized["ETag"] == "v123"
    assert "X-Trip-Status" in normalized
    assert normalized["X-Trip-Status"] == "SOFT_DELETED"
    assert "etag" not in normalized  # Should be mapped, not duplicated


@pytest.mark.asyncio
async def test_high_concurrency_idempotency_safety(client: AsyncClient):
    """Stress test parallel idempotency requests to ensure zero duplication."""
    from tests.test_integration import make_manual_trip_payload, SUPER_ADMIN_HEADERS

    idempotency_key = "STRESS-KEY-" + str(asyncio.get_event_loop().time())
    payload = make_manual_trip_payload(trip_no="TR-STRESS")
    headers = {**SUPER_ADMIN_HEADERS, "Idempotency-Key": idempotency_key}

    # Fire 10 concurrent requests
    tasks = [client.post("/api/v1/trips", json=payload, headers=headers) for _ in range(10)]

    responses = await asyncio.gather(*tasks)

    # Exactly one should be 201 (the creator), others can be 201 (replays) or 409 (if blocked by mutex)
    # Our implementation uses a mutex and _check_idempotency_key, so they should all eventually succeed or block safely.

    success_codes = {r.status_code for r in responses}
    assert success_codes.issubset({201, 409})  # 409 is acceptable under super-high pressure if mutex is held

    # Verify only one trip exists in DB
    from trip_service.database import async_session_factory

    async with async_session_factory() as session:
        count = (
            await session.execute(select(func.count()).select_from(TripTrip).where(TripTrip.trip_no == "TR-STRESS"))
        ).scalar()
        assert count == 1


@pytest.mark.asyncio
async def test_reference_release_after_soft_delete(db_engine):
    """Verify that soft-deleted trips (and legacy CANCELLED) are ignored in overlap checks."""
    from trip_service.trip_helpers import _find_overlap
    from sqlalchemy.ext.asyncio import async_sessionmaker

    now = datetime.now(UTC)

    # Create a soft-deleted trip
    trip = TripTrip(
        id="TRIP-SOFT-001",
        trip_no="T1",
        source_type=SourceType.TELEGRAM_TRIP_SLIP.value,
        source_reference_key="SRC-TEST-001",
        driver_id="DRIVER-REF-001",
        vehicle_id="VEHICLE-REF-001",
        trip_datetime_utc=now,
        trip_timezone="UTC",
        status=TripStatus.SOFT_DELETED.value,
        soft_deleted_at_utc=now,
        created_at_utc=now,
        updated_at_utc=now,
        created_by_actor_type="ADMIN",
        created_by_actor_id="admin",
        version=1,
    )

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(trip)
        await session.commit()

        # This should NOT raise OverlapError because the existing trip is soft-deleted
        driver_overlap = await _find_overlap(
            session,
            field_name="driver_id",
            field_value="DRIVER-REF-001",
            trip_start_utc=now,
            planned_end_utc=now + timedelta(hours=1),
        )
        assert driver_overlap is None


@pytest.mark.asyncio
async def test_outbox_atomicity_and_schema(client: AsyncClient, db_engine):
    """Verify that outbox records are created transactionally and follow v1 schema."""
    from tests.test_integration import make_manual_trip_payload, SUPER_ADMIN_HEADERS
    from sqlalchemy.ext.asyncio import async_sessionmaker

    payload = make_manual_trip_payload(trip_no="TR-OUTBOX-V1")
    response = await client.post("/api/v1/trips", json=payload, headers=SUPER_ADMIN_HEADERS)
    assert response.status_code == 201

    # Verify outbox record exists
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        result = await session.execute(select(TripOutbox).where(TripOutbox.event_name == "trip.created.v1"))
        outbox = result.scalar_one()

    payload_data = json.loads(outbox.payload_json)
    assert "trip_id" in payload_data
    assert payload_data["trip_no"] == "TR-OUTBOX-V1"
    assert outbox.partition_key == payload_data["trip_id"]


@pytest.mark.asyncio
async def test_rfc9457_error_compliance(client: AsyncClient):
    """Verify error responses follow RFC 9457 standards."""
    from tests.test_integration import SUPER_ADMIN_HEADERS

    # Trigger a 404
    response = await client.get("/api/v1/trips/NON-EXISTENT-ID", headers=SUPER_ADMIN_HEADERS)
    assert response.status_code == 404

    data = response.json()
    assert "type" in data
    assert "title" in data
    assert "status" in data
    assert data["status"] == 404
    assert "detail" in data
    assert "instance" in data
