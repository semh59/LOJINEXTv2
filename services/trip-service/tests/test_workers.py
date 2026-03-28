"""Worker-level behavior tests for retry and outbox contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from trip_service.broker import MessageBroker, OutboxMessage
from trip_service.config import settings
from trip_service.models import TripOutbox, TripTrip, TripTripEnrichment
from trip_service.workers.enrichment_worker import _claim_and_process_batch
from trip_service.workers.outbox_relay import _outbox_next_attempt_at, _publish_single


class FailingBroker(MessageBroker):
    """Broker stub that always fails publishes."""

    async def publish(self, message: OutboxMessage) -> None:
        raise RuntimeError("publish failed")

    async def close(self) -> None:
        return None

    async def check_health(self) -> None:
        return None


@pytest.mark.asyncio
async def test_outbox_first_failure_backoff_is_five_seconds(test_session):
    row = TripOutbox(
        event_id="01JATWORKEROUTBOX000000001",
        aggregate_type="TRIP",
        aggregate_id="01JATWORKERTRIP000000001",
        aggregate_version=1,
        event_name="trip.created.v1",
        schema_version=1,
        payload_json="{}",
        partition_key="01JATWORKERTRIP000000001",
        publish_status="PENDING",
        attempt_count=0,
        created_at_utc=datetime.now(UTC),
    )

    before = datetime.now(UTC)
    success = await _publish_single(FailingBroker(), test_session, row)
    after = datetime.now(UTC)

    assert success is False
    assert row.publish_status == "FAILED"
    assert row.next_attempt_at_utc is not None
    assert before + timedelta(seconds=4) <= row.next_attempt_at_utc <= after + timedelta(seconds=6)


@pytest.mark.asyncio
async def test_outbox_dead_letters_at_configured_ceiling(test_session, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "outbox_relay_max_failures", 2)
    row = TripOutbox(
        event_id="01JATWORKEROUTBOX000000002",
        aggregate_type="TRIP",
        aggregate_id="01JATWORKERTRIP000000002",
        aggregate_version=1,
        event_name="trip.created.v1",
        schema_version=1,
        payload_json="{}",
        partition_key="01JATWORKERTRIP000000002",
        publish_status="FAILED",
        attempt_count=1,
        created_at_utc=datetime.now(UTC),
    )

    success = await _publish_single(FailingBroker(), test_session, row)
    assert success is False
    assert row.publish_status == "DEAD_LETTER"
    assert row.next_attempt_at_utc is None


@pytest.mark.asyncio
async def test_claim_batch_skips_failed_rows_at_retry_ceiling(test_session, db_engine, monkeypatch: pytest.MonkeyPatch):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr("trip_service.workers.enrichment_worker.async_session_factory", session_factory)
    now = datetime.now(UTC)
    trip = TripTrip(
        id="01JATWORKERTRIP000000003",
        trip_no="TR-WORKER-RETRY-CEILING",
        source_type="TELEGRAM_TRIP_SLIP",
        source_slip_no="SLIP-WORKER-RETRY-CEILING",
        source_reference_key="telegram-message-worker-retry",
        source_payload_hash="hash",
        review_reason_code="SOURCE_IMPORT",
        base_trip_id=None,
        driver_id="driver-001",
        vehicle_id="vehicle-001",
        trailer_id=None,
        route_pair_id="pair-001",
        route_id="route-ist-ank",
        origin_location_id="loc-istanbul",
        origin_name_snapshot="Istanbul",
        destination_location_id="loc-ankara",
        destination_name_snapshot="Ankara",
        trip_datetime_utc=now,
        trip_timezone="Europe/Istanbul",
        planned_duration_s=21600,
        planned_end_utc=now + timedelta(hours=6),
        tare_weight_kg=10000,
        gross_weight_kg=25000,
        net_weight_kg=15000,
        is_empty_return=False,
        status="PENDING_REVIEW",
        version=1,
        created_by_actor_type="SERVICE",
        created_by_actor_id="worker-test",
        created_at_utc=now,
        updated_at_utc=now,
    )
    enrichment = TripTripEnrichment(
        id="01JATWORKERENRICH000000001",
        trip_id=trip.id,
        enrichment_status="FAILED",
        route_status="FAILED",
        data_quality_flag="LOW",
        enrichment_attempt_count=settings.enrichment_max_attempts,
        next_retry_at_utc=now - timedelta(minutes=1),
        created_at_utc=now,
        updated_at_utc=now,
    )
    test_session.add(trip)
    test_session.add(enrichment)
    await test_session.commit()

    processed = await _claim_and_process_batch("worker-test")
    assert processed == 0


def test_outbox_backoff_helper_caps_after_fifth_window():
    now = datetime.now(UTC)
    next_attempt = _outbox_next_attempt_at(6)
    assert next_attempt >= now + timedelta(seconds=300)
