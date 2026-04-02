"""Unit tests for trip helpers and pure contract logic."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from trip_service.dependencies import LocationTripContext
from trip_service.models import TripTrip, TripTripEvidence
from trip_service.observability import _sleep_with_heartbeats
from trip_service.trip_helpers import apply_trip_context, latest_evidence, trip_complete_errors, utc_now


def _base_trip() -> TripTrip:
    now = datetime.now(UTC)
    return TripTrip(
        id="01JATUNITTRIP00000000000001",
        trip_no="TR-UNIT-001",
        source_type="ADMIN_MANUAL",
        source_slip_no=None,
        source_reference_key=None,
        source_payload_hash=None,
        review_reason_code=None,
        base_trip_id=None,
        driver_id="driver-001",
        vehicle_id="vehicle-001",
        trailer_id=None,
        route_pair_id=None,
        route_id=None,
        origin_location_id=None,
        origin_name_snapshot=None,
        destination_location_id=None,
        destination_name_snapshot=None,
        trip_datetime_utc=now,
        trip_timezone="Europe/Istanbul",
        planned_duration_s=None,
        planned_end_utc=None,
        tare_weight_kg=10000,
        gross_weight_kg=25000,
        net_weight_kg=15000,
        is_empty_return=False,
        status="PENDING_REVIEW",
        version=1,
        created_by_actor_type="ADMIN",
        created_by_actor_id="admin-001",
        created_at_utc=now,
        updated_at_utc=now,
    )


def test_latest_evidence_prefers_newest_created_at() -> None:
    trip = _base_trip()
    first = TripTripEvidence(
        id="01JATEVIDENCE000000000000001",
        trip_id=trip.id,
        evidence_source="TELEGRAM_TRIP_SLIP",
        evidence_kind="SLIP_IMAGE",
        created_at_utc=datetime(2026, 3, 27, 10, 0, tzinfo=UTC),
    )
    second = TripTripEvidence(
        id="01JATEVIDENCE000000000000002",
        trip_id=trip.id,
        evidence_source="TELEGRAM_TRIP_SLIP",
        evidence_kind="SLIP_IMAGE",
        created_at_utc=datetime(2026, 3, 27, 11, 0, tzinfo=UTC),
    )
    trip.evidence = [first, second]

    assert latest_evidence(trip) == second


def test_apply_trip_context_forward_and_reverse() -> None:
    trip = _base_trip()
    context = LocationTripContext(
        pair_id="pair-001",
        origin_location_id="loc-1",
        origin_name="Istanbul",
        destination_location_id="loc-2",
        destination_name="Ankara",
        forward_route_id="route-fwd",
        forward_duration_s=21600,
        reverse_route_id="route-rev",
        reverse_duration_s=22000,
        profile_code="TIR",
        pair_status="ACTIVE",
    )

    apply_trip_context(trip, context, reverse=False)
    assert trip.route_id == "route-fwd"
    assert trip.origin_name_snapshot == "Istanbul"
    assert trip.destination_name_snapshot == "Ankara"
    assert trip.planned_end_utc is not None

    reverse_trip = _base_trip()
    apply_trip_context(reverse_trip, context, reverse=True)
    assert reverse_trip.route_id == "route-rev"
    assert reverse_trip.origin_name_snapshot == "Ankara"
    assert reverse_trip.destination_name_snapshot == "Istanbul"


def test_trip_complete_errors_lists_missing_fields() -> None:
    trip = _base_trip()
    errors = trip_complete_errors(trip)
    fields = {error["field"] for error in errors}
    assert "body.route_pair_id" in fields
    assert "body.route_id" in fields
    assert "body.origin_name_snapshot" in fields
    assert "body.destination_name_snapshot" in fields


def test_utc_now_is_timezone_aware() -> None:
    assert utc_now().tzinfo == UTC


@pytest.mark.asyncio
async def test_cleanup_heartbeat_sleep_chunks_long_intervals(monkeypatch: pytest.MonkeyPatch) -> None:
    heartbeat_calls: list[str] = []
    sleep_calls: list[int] = []

    async def fake_record_worker_heartbeat(worker_name: str, recorded_at_utc: datetime | None = None) -> None:
        del recorded_at_utc
        heartbeat_calls.append(worker_name)

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(int(seconds))

    monkeypatch.setattr("trip_service.observability.record_worker_heartbeat", fake_record_worker_heartbeat)
    monkeypatch.setattr("trip_service.observability.asyncio.sleep", fake_sleep)

    await _sleep_with_heartbeats("cleanup-worker", 35)

    assert heartbeat_calls == ["cleanup-worker", "cleanup-worker", "cleanup-worker"]
    assert sleep_calls == [15, 15, 5]
