"""Worker-level behavior tests for retry and outbox contracts."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

import trip_service.workers.enrichment_worker as enrichment_worker_module
import trip_service.workers.outbox_relay as outbox_relay_module
from trip_service.broker import MessageBroker, OutboxMessage
from trip_service.config import settings
from trip_service.enums import EnrichmentStatus, RouteStatus
from trip_service.models import TripOutbox, TripTrip, TripTripEnrichment, TripTripEvidence
from trip_service.workers.enrichment_worker import (
    _claim_and_process_batch,
    _compute_data_quality_flag,
    _derive_final_enrichment_status,
    _enrichment_next_retry_at,
    _is_schema_not_ready,
    _process_single_enrichment,
    _resolve_route,
    run_enrichment_worker,
)
from trip_service.workers.outbox_relay import (
    _outbox_next_attempt_at,
    _publish_single,
    _relay_batch,
    run_outbox_relay,
)


class FailingBroker(MessageBroker):
    """Broker stub that always fails publishes."""

    async def publish(self, message: OutboxMessage) -> None:
        raise RuntimeError("publish failed")

    async def close(self) -> None:
        return None

    async def check_health(self) -> None:
        return None


class RecordingBroker(MessageBroker):
    """Broker stub that records published messages."""

    def __init__(self) -> None:
        self.messages: list[OutboxMessage] = []

    async def publish(self, message: OutboxMessage) -> None:
        self.messages.append(message)

    async def close(self) -> None:
        return None

    async def check_health(self) -> None:
        return None


class SelectiveFailBroker(MessageBroker):
    """Broker stub that fails selected event ids while recording successes."""

    def __init__(self, failing_event_ids: set[str]) -> None:
        self.failing_event_ids = failing_event_ids
        self.messages: list[OutboxMessage] = []

    async def publish(self, message: OutboxMessage) -> None:
        if message.event_id in self.failing_event_ids:
            raise RuntimeError(f"publish failed for {message.event_id}")
        self.messages.append(message)

    async def close(self) -> None:
        return None

    async def check_health(self) -> None:
        return None


def test_enrichment_helper_functions_cover_backoff_and_status_derivation(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed_now = datetime(2026, 4, 5, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(enrichment_worker_module, "_now_utc", lambda: fixed_now)
    monkeypatch.setattr(enrichment_worker_module.random, "random", lambda: 0.5)

    assert _enrichment_next_retry_at(0) == fixed_now + timedelta(seconds=60)
    assert _enrichment_next_retry_at(99) == fixed_now + timedelta(seconds=21600)
    assert _is_schema_not_ready(
        DBAPIError("SELECT 1", {}, Exception("relation trip_trips does not exist"), False)
    )
    assert (
        _is_schema_not_ready(DBAPIError("SELECT 1", {}, Exception("relation other_table does not exist"), False))
        is False
    )
    assert _compute_data_quality_flag("ADMIN_MANUAL", None, route_resolved=False) == "HIGH"
    assert _compute_data_quality_flag("TELEGRAM_TRIP_SLIP", 0.75, route_resolved=True) == "MEDIUM"
    assert _compute_data_quality_flag("TELEGRAM_TRIP_SLIP", None, route_resolved=False) == "MEDIUM"
    assert _derive_final_enrichment_status(RouteStatus.READY) == EnrichmentStatus.READY
    assert _derive_final_enrichment_status(RouteStatus.SKIPPED) == EnrichmentStatus.SKIPPED
    assert _derive_final_enrichment_status(RouteStatus.FAILED) == EnrichmentStatus.FAILED
    assert _derive_final_enrichment_status(RouteStatus.PENDING) == EnrichmentStatus.PENDING


@pytest.mark.asyncio
async def test_outbox_first_failure_backoff_is_five_seconds(
    test_session,
    db_engine,
    monkeypatch: pytest.MonkeyPatch,
):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr("trip_service.workers.outbox_relay.async_session_factory", session_factory)
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
    test_session.add(row)
    await test_session.commit()

    before = datetime.now(UTC)
    processed = await _relay_batch(FailingBroker(), worker_id="test-worker", batch_size=10)
    after = datetime.now(UTC)

    assert processed == 0
    async with session_factory() as session:
        refreshed = await session.get(TripOutbox, row.event_id)
    assert refreshed is not None
    assert refreshed.publish_status == "FAILED"
    assert refreshed.last_error_code == "publish failed"
    assert refreshed.next_attempt_at_utc is not None
    assert before + timedelta(seconds=4) <= refreshed.next_attempt_at_utc <= after + timedelta(seconds=6)


@pytest.mark.asyncio
async def test_outbox_dead_letters_at_configured_ceiling(
    test_session,
    db_engine,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "outbox_relay_max_failures", 2)
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr("trip_service.workers.outbox_relay.async_session_factory", session_factory)
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
    test_session.add(row)
    await test_session.commit()

    processed = await _relay_batch(FailingBroker(), worker_id="test-worker", batch_size=10)
    assert processed == 0

    async with session_factory() as session:
        refreshed = await session.get(TripOutbox, row.event_id)
    assert refreshed is not None
    assert refreshed.publish_status == "DEAD_LETTER"
    assert refreshed.next_attempt_at_utc is None
    assert refreshed.last_error_code == "publish failed"


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


@pytest.mark.asyncio
async def test_outbox_relay_skips_publishing_rows(test_session, db_engine, monkeypatch: pytest.MonkeyPatch):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr("trip_service.workers.outbox_relay.async_session_factory", session_factory)

    now = datetime.now(UTC)
    pending = TripOutbox(
        event_id="01JATOUTBOXPENDING000001",
        aggregate_type="TRIP",
        aggregate_id="01JATOUTBOXPENDINGTRIP1",
        aggregate_version=1,
        event_name="trip.created.v1",
        schema_version=1,
        payload_json="{}",
        partition_key="01JATOUTBOXPENDINGTRIP1",
        publish_status="PENDING",
        attempt_count=0,
        created_at_utc=now,
    )
    publishing = TripOutbox(
        event_id="01JATOUTBOXPUBLISHING001",
        aggregate_type="TRIP",
        aggregate_id="01JATOUTBOXPUBLISHING1",
        aggregate_version=1,
        event_name="trip.created.v1",
        schema_version=1,
        payload_json="{}",
        partition_key="01JATOUTBOXPUBLISHING1",
        publish_status="PUBLISHING",
        attempt_count=0,
        created_at_utc=now,
    )
    ready = TripOutbox(
        event_id="01JATOUTBOXREADY0000001",
        aggregate_type="TRIP",
        aggregate_id="01JATOUTBOXREADYTRIP1",
        aggregate_version=1,
        event_name="trip.created.v1",
        schema_version=1,
        payload_json="{}",
        partition_key="01JATOUTBOXREADYTRIP1",
        publish_status="READY",
        attempt_count=0,
        created_at_utc=now,
    )
    test_session.add_all([pending, publishing, ready])
    await test_session.commit()

    broker = RecordingBroker()
    processed = await _relay_batch(broker, worker_id="test-worker", batch_size=10)
    assert processed == 2
    assert len(broker.messages) == 2
    assert {msg.event_id for msg in broker.messages} == {pending.event_id, ready.event_id}

    async with session_factory() as session:
        refreshed_pending = await session.get(TripOutbox, pending.event_id)
        refreshed_publishing = await session.get(TripOutbox, publishing.event_id)
        refreshed_ready = await session.get(TripOutbox, ready.event_id)
    assert refreshed_pending is not None
    assert refreshed_pending.publish_status == "PUBLISHED"
    assert refreshed_publishing is not None
    assert refreshed_publishing.publish_status == "PUBLISHING"
    assert refreshed_ready is not None
    assert refreshed_ready.publish_status == "PUBLISHED"


@pytest.mark.asyncio
async def test_enrichment_reclaims_stale_claim(test_session, db_engine, monkeypatch: pytest.MonkeyPatch):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr("trip_service.workers.enrichment_worker.async_session_factory", session_factory)

    async def stub_resolve_route(origin_name: str, destination_name: str):
        del origin_name, destination_name
        return "route-resolved-001", RouteStatus.READY

    monkeypatch.setattr("trip_service.workers.enrichment_worker._resolve_route", stub_resolve_route)

    now = datetime.now(UTC)
    trip = TripTrip(
        id="01JATENRICHSTALEROW001",
        trip_no="TR-ENRICH-STALE",
        source_type="TELEGRAM_TRIP_SLIP",
        source_slip_no="SLIP-ENRICH-STALE",
        source_reference_key="telegram-message-enrich-stale",
        source_payload_hash="hash",
        review_reason_code="SOURCE_IMPORT",
        base_trip_id=None,
        driver_id="driver-001",
        vehicle_id="vehicle-001",
        trailer_id=None,
        route_pair_id="pair-001",
        route_id=None,
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
    evidence = TripTripEvidence(
        id="01JATENRICHSTALEROW002",
        trip_id=trip.id,
        evidence_source="TELEGRAM_TRIP_SLIP",
        evidence_kind="OCR",
        source_slip_no="SLIP-ENRICH-STALE",
        origin_name_raw="Istanbul",
        destination_name_raw="Ankara",
        raw_payload_json="{}",
        created_at_utc=now,
    )
    enrichment = TripTripEnrichment(
        id="01JATENRICHSTALEROW003",
        trip_id=trip.id,
        enrichment_status=EnrichmentStatus.RUNNING,
        route_status=RouteStatus.PENDING,
        data_quality_flag="LOW",
        enrichment_attempt_count=0,
        next_retry_at_utc=None,
        claim_token="stale-claim",
        claim_expires_at_utc=now - timedelta(minutes=5),
        claimed_by_worker="old-worker",
        created_at_utc=now,
        updated_at_utc=now,
    )
    test_session.add(trip)
    test_session.add(evidence)
    test_session.add(enrichment)
    await test_session.commit()

    processed = await _claim_and_process_batch("worker-test")
    assert processed == 1

    async with session_factory() as session:
        refreshed = await session.get(TripTripEnrichment, enrichment.id)
    assert refreshed is not None
    assert refreshed.enrichment_status == EnrichmentStatus.READY
    assert refreshed.claim_token is None


@pytest.mark.asyncio
async def test_enrichment_skips_non_retryable_location_business_invalid(
    test_session,
    db_engine,
    monkeypatch: pytest.MonkeyPatch,
):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr("trip_service.workers.enrichment_worker.async_session_factory", session_factory)

    async def skipped_route_resolution(origin_name: str, destination_name: str):
        del origin_name, destination_name
        return None, RouteStatus.SKIPPED

    monkeypatch.setattr("trip_service.workers.enrichment_worker._resolve_route", skipped_route_resolution)

    now = datetime.now(UTC)
    trip = TripTrip(
        id="01JATENRICHSKIPPED0001",
        trip_no="TR-ENRICH-SKIPPED",
        source_type="TELEGRAM_TRIP_SLIP",
        source_slip_no="SLIP-ENRICH-SKIPPED",
        source_reference_key="telegram-message-enrich-skipped",
        source_payload_hash="hash",
        review_reason_code="SOURCE_IMPORT",
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
        created_by_actor_type="SERVICE",
        created_by_actor_id="worker-test",
        created_at_utc=now,
        updated_at_utc=now,
    )
    evidence = TripTripEvidence(
        id="01JATENRICHSKIPPED0002",
        trip_id=trip.id,
        evidence_source="TELEGRAM_TRIP_SLIP",
        evidence_kind="OCR",
        source_slip_no="SLIP-ENRICH-SKIPPED",
        origin_name_raw="Unknown Origin",
        destination_name_raw="Unknown Destination",
        raw_payload_json="{}",
        created_at_utc=now,
    )
    enrichment = TripTripEnrichment(
        id="01JATENRICHSKIPPED0003",
        trip_id=trip.id,
        enrichment_status=EnrichmentStatus.PENDING,
        route_status=RouteStatus.PENDING,
        data_quality_flag="LOW",
        enrichment_attempt_count=0,
        next_retry_at_utc=None,
        created_at_utc=now,
        updated_at_utc=now,
    )
    test_session.add_all([trip, evidence, enrichment])
    await test_session.commit()

    processed = await _claim_and_process_batch("worker-test")
    assert processed == 1

    async with session_factory() as session:
        refreshed = await session.get(TripTripEnrichment, enrichment.id)
    assert refreshed is not None
    assert refreshed.route_status == RouteStatus.SKIPPED
    assert refreshed.enrichment_status == EnrichmentStatus.SKIPPED
    assert refreshed.next_retry_at_utc is None


@pytest.mark.asyncio
async def test_outbox_relay_reclaims_stale_claim(test_session, db_engine, monkeypatch: pytest.MonkeyPatch):
    """Ensure outbox relay reclaims rows stuck in PUBLISHING with expired claims."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr("trip_service.workers.outbox_relay.async_session_factory", session_factory)

    now = datetime.now(UTC)
    stale_publishing = TripOutbox(
        event_id="01JATSTALEOUTBOX001",
        aggregate_type="TRIP",
        aggregate_id="TRIP-STALE-001",
        aggregate_version=1,
        event_name="trip.created.v1",
        schema_version=1,
        payload_json="{}",
        partition_key="TRIP-STALE-001",
        publish_status="PUBLISHING",
        attempt_count=1,
        claim_token="old-token",
        claim_expires_at_utc=now - timedelta(minutes=10),
        claimed_by_worker="dead-worker",
        created_at_utc=now - timedelta(hours=1),
    )
    test_session.add(stale_publishing)
    await test_session.commit()

    broker = RecordingBroker()
    processed = await _relay_batch(broker, worker_id="new-worker", batch_size=10)

    assert processed == 1
    assert len(broker.messages) == 1
    assert broker.messages[0].event_id == stale_publishing.event_id

    async with session_factory() as session:
        refreshed = await session.get(TripOutbox, stale_publishing.event_id)
    assert refreshed is not None
    assert refreshed.publish_status == "PUBLISHED"
    assert refreshed.claim_token is None
    assert refreshed.claimed_by_worker is None


@pytest.mark.asyncio
async def test_outbox_relay_commits_each_event_independently(test_session, db_engine, monkeypatch: pytest.MonkeyPatch):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr("trip_service.workers.outbox_relay.async_session_factory", session_factory)

    now = datetime.now(UTC)
    first = TripOutbox(
        event_id="01JATOUTBOXISOLATION000001",
        aggregate_type="TRIP",
        aggregate_id="TRIP-ISOLATION-001",
        aggregate_version=1,
        event_name="trip.created.v1",
        schema_version=1,
        payload_json="{}",
        partition_key="TRIP-ISOLATION-001",
        publish_status="PENDING",
        attempt_count=0,
        created_at_utc=now,
    )
    second = TripOutbox(
        event_id="01JATOUTBOXISOLATION000002",
        aggregate_type="TRIP",
        aggregate_id="TRIP-ISOLATION-002",
        aggregate_version=1,
        event_name="trip.created.v1",
        schema_version=1,
        payload_json="{}",
        partition_key="TRIP-ISOLATION-002",
        publish_status="PENDING",
        attempt_count=0,
        created_at_utc=now + timedelta(seconds=1),
    )
    test_session.add_all([first, second])
    await test_session.commit()

    broker = SelectiveFailBroker({second.event_id})
    processed = await _relay_batch(broker, worker_id="test-worker", batch_size=10)

    assert processed == 1
    assert [message.event_id for message in broker.messages] == [first.event_id]

    async with session_factory() as session:
        refreshed_first = await session.get(TripOutbox, first.event_id)
        refreshed_second = await session.get(TripOutbox, second.event_id)

    assert refreshed_first is not None
    assert refreshed_first.publish_status == "PUBLISHED"
    assert refreshed_first.last_error_code is None
    assert refreshed_first.claim_token is None

    assert refreshed_second is not None
    assert refreshed_second.publish_status == "FAILED"
    assert refreshed_second.last_error_code == f"publish failed for {second.event_id}"[:100]
    assert refreshed_second.claim_token is None


@pytest.mark.asyncio
async def test_enrichment_resolve_route_awaits_service_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class StubWorkerClient:
        async def post(self, url: str, *, json: dict[str, object], headers: dict[str, str]):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return httpx.Response(200, json={"route_id": "route-123"}, request=httpx.Request("POST", url))

    async def fake_get_worker_client() -> StubWorkerClient:
        return StubWorkerClient()

    async def fake_location_headers() -> dict[str, str]:
        return {"Authorization": "Bearer worker-token"}

    monkeypatch.setattr("trip_service.workers.enrichment_worker.get_worker_client", fake_get_worker_client)
    monkeypatch.setattr("trip_service.workers.enrichment_worker._location_service_headers", fake_location_headers)

    route_id, status = await _resolve_route("Istanbul", "Ankara")

    assert route_id == "route-123"
    assert status == RouteStatus.READY
    assert captured["headers"] == {"Authorization": "Bearer worker-token"}


@pytest.mark.asyncio
async def test_enrichment_resolve_route_handles_business_invalid_and_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_location_headers() -> dict[str, str]:
        return {"Authorization": "Bearer worker-token"}

    class StubWorkerClient:
        def __init__(self, response: httpx.Response | Exception) -> None:
            self.response = response

        async def post(self, url: str, *, json: dict[str, object], headers: dict[str, str]):
            del url, json, headers
            if isinstance(self.response, Exception):
                raise self.response
            return self.response

    async def fake_worker_client_skip() -> StubWorkerClient:
        return StubWorkerClient(
            httpx.Response(
                404,
                json={"code": "LOCATION_ROUTE_RESOLUTION_NOT_FOUND"},
                request=httpx.Request("POST", "http://location/internal/v1/routes/resolve"),
            )
        )

    async def fake_worker_client_fail() -> StubWorkerClient:
        return StubWorkerClient(
            httpx.Response(
                500,
                json={"code": "BOOM"},
                request=httpx.Request("POST", "http://location/internal/v1/routes/resolve"),
            )
        )

    async def fake_worker_client_error() -> StubWorkerClient:
        return StubWorkerClient(httpx.ConnectError("down"))

    monkeypatch.setattr("trip_service.workers.enrichment_worker._location_service_headers", fake_location_headers)
    monkeypatch.setattr("trip_service.workers.enrichment_worker.get_worker_client", fake_worker_client_skip)
    assert await _resolve_route("Istanbul", "Ankara") == (None, RouteStatus.SKIPPED)

    monkeypatch.setattr("trip_service.workers.enrichment_worker.get_worker_client", fake_worker_client_fail)
    assert await _resolve_route("Istanbul", "Ankara") == (None, RouteStatus.FAILED)

    monkeypatch.setattr("trip_service.workers.enrichment_worker.get_worker_client", fake_worker_client_error)
    assert await _resolve_route("Istanbul", "Ankara") == (None, RouteStatus.FAILED)


@pytest.mark.asyncio
async def test_process_single_enrichment_marks_missing_evidence_failed(
    test_session,
    db_engine,
    monkeypatch: pytest.MonkeyPatch,
):
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr("trip_service.workers.enrichment_worker.async_session_factory", session_factory)

    now = datetime.now(UTC)
    trip = TripTrip(
        id="01JATENRICHMISSEVIDENCE001",
        trip_no="TR-ENRICH-MISSING-EVIDENCE",
        source_type="TELEGRAM_TRIP_SLIP",
        source_slip_no="SLIP-ENRICH-MISSING",
        source_reference_key="telegram-message-enrich-missing",
        source_payload_hash="hash",
        review_reason_code="SOURCE_IMPORT",
        base_trip_id=None,
        driver_id="driver-001",
        vehicle_id="vehicle-001",
        trailer_id=None,
        route_pair_id="pair-001",
        route_id=None,
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
        id="01JATENRICHMISSEVIDENCE002",
        trip_id=trip.id,
        enrichment_status=EnrichmentStatus.RUNNING,
        route_status=RouteStatus.PENDING,
        data_quality_flag="LOW",
        enrichment_attempt_count=0,
        next_retry_at_utc=None,
        claim_token="claim-token",
        claim_expires_at_utc=now + timedelta(minutes=5),
        claimed_by_worker="worker-test",
        created_at_utc=now,
        updated_at_utc=now,
    )
    test_session.add_all([trip, enrichment])
    await test_session.commit()

    await _process_single_enrichment(trip.id, enrichment.id, "claim-token", "worker-test")

    async with session_factory() as session:
        refreshed = await session.get(TripTripEnrichment, enrichment.id)
    assert refreshed is not None
    assert refreshed.route_status == RouteStatus.FAILED
    assert refreshed.enrichment_status == EnrichmentStatus.FAILED
    assert refreshed.next_retry_at_utc is not None
    assert refreshed.claim_token is None


@pytest.mark.asyncio
async def test_process_single_enrichment_leaves_ready_rows_without_retry(
    test_session,
    db_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr("trip_service.workers.enrichment_worker.async_session_factory", session_factory)

    now = datetime.now(UTC)
    trip = TripTrip(
        id="01JATENRICHREADYROW000001",
        trip_no="TR-ENRICH-READY",
        source_type="ADMIN_MANUAL",
        source_slip_no=None,
        source_reference_key=None,
        source_payload_hash="hash",
        review_reason_code=None,
        base_trip_id=None,
        driver_id="driver-001",
        vehicle_id="vehicle-001",
        trailer_id=None,
        route_pair_id="pair-001",
        route_id="route-001",
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
        created_by_actor_type="MANAGER",
        created_by_actor_id="manager-001",
        created_at_utc=now,
        updated_at_utc=now,
    )
    enrichment = TripTripEnrichment(
        id="01JATENRICHREADYROW000002",
        trip_id=trip.id,
        enrichment_status=EnrichmentStatus.RUNNING,
        route_status=RouteStatus.READY,
        data_quality_flag="LOW",
        enrichment_attempt_count=0,
        next_retry_at_utc=now + timedelta(minutes=5),
        claim_token="claim-token",
        claim_expires_at_utc=now + timedelta(minutes=5),
        claimed_by_worker="worker-test",
        created_at_utc=now,
        updated_at_utc=now,
    )
    test_session.add_all([trip, enrichment])
    await test_session.commit()

    await _process_single_enrichment(trip.id, enrichment.id, "claim-token", "worker-test")

    async with session_factory() as session:
        refreshed = await session.get(TripTripEnrichment, enrichment.id)
    assert refreshed is not None
    assert refreshed.enrichment_status == EnrichmentStatus.READY
    assert refreshed.data_quality_flag == "HIGH"
    assert refreshed.next_retry_at_utc is None


@pytest.mark.asyncio
async def test_process_single_enrichment_stops_retrying_at_failure_ceiling(
    test_session,
    db_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr("trip_service.workers.enrichment_worker.async_session_factory", session_factory)
    monkeypatch.setattr(settings, "enrichment_max_attempts", 1)

    now = datetime.now(UTC)
    trip = TripTrip(
        id="01JATENRICHFAILCEIL000001",
        trip_no="TR-ENRICH-FAIL-CEIL",
        source_type="TELEGRAM_TRIP_SLIP",
        source_slip_no="SLIP-FAIL-CEIL",
        source_reference_key="telegram-message-fail-ceil",
        source_payload_hash="hash",
        review_reason_code="SOURCE_IMPORT",
        base_trip_id=None,
        driver_id="driver-001",
        vehicle_id="vehicle-001",
        trailer_id=None,
        route_pair_id="pair-001",
        route_id=None,
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
        id="01JATENRICHFAILCEIL000002",
        trip_id=trip.id,
        enrichment_status=EnrichmentStatus.RUNNING,
        route_status=RouteStatus.PENDING,
        data_quality_flag="LOW",
        enrichment_attempt_count=1,
        next_retry_at_utc=None,
        claim_token="claim-token",
        claim_expires_at_utc=now + timedelta(minutes=5),
        claimed_by_worker="worker-test",
        created_at_utc=now,
        updated_at_utc=now,
    )
    evidence = TripTripEvidence(
        id="01JATENRICHFAILCEIL000003",
        trip_id=trip.id,
        evidence_source="TELEGRAM_TRIP_SLIP",
        evidence_kind="OCR",
        source_slip_no="SLIP-FAIL-CEIL",
        origin_name_raw="Istanbul",
        destination_name_raw="Ankara",
        raw_payload_json="{}",
        created_at_utc=now,
    )
    test_session.add_all([trip, enrichment, evidence])
    await test_session.commit()

    async def explode_route(origin_name: str, destination_name: str):
        del origin_name, destination_name
        raise RuntimeError("route exploded")

    monkeypatch.setattr("trip_service.workers.enrichment_worker._resolve_route", explode_route)

    await _process_single_enrichment(trip.id, enrichment.id, "claim-token", "worker-test")

    async with session_factory() as session:
        refreshed = await session.get(TripTripEnrichment, enrichment.id)
    assert refreshed is not None
    assert refreshed.enrichment_status == EnrichmentStatus.FAILED
    assert refreshed.next_retry_at_utc is None
    assert refreshed.last_enrichment_error_code == "route exploded"


@pytest.mark.asyncio
async def test_publish_single_returns_false_when_claim_is_lost(db_engine, monkeypatch: pytest.MonkeyPatch) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr("trip_service.workers.outbox_relay.async_session_factory", session_factory)

    result = await _publish_single(RecordingBroker(), "missing-event", "missing-claim")

    assert result is False


@pytest.mark.asyncio
async def test_claim_and_process_batch_returns_zero_when_no_rows(db_engine, monkeypatch: pytest.MonkeyPatch) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr("trip_service.workers.enrichment_worker.async_session_factory", session_factory)

    assert await _claim_and_process_batch("worker-empty") == 0


@pytest.mark.asyncio
async def test_run_enrichment_worker_warns_when_schema_is_not_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_claim(worker_id: str, batch_size: int = 10) -> int:
        del worker_id, batch_size
        raise DBAPIError("SELECT 1", {}, Exception("relation trip_trip_enrichment does not exist"), False)

    async def stop_sleep(seconds: float) -> None:
        del seconds
        raise asyncio.CancelledError

    warnings: list[str] = []

    def fake_warning(message: str, *args) -> None:
        warnings.append(message % args if args else message)

    monkeypatch.setattr("trip_service.workers.enrichment_worker._claim_and_process_batch", fail_claim)
    monkeypatch.setattr("trip_service.workers.enrichment_worker.asyncio.sleep", stop_sleep)
    monkeypatch.setattr(enrichment_worker_module.logger, "warning", fake_warning)

    with pytest.raises(asyncio.CancelledError):
        await run_enrichment_worker(worker_id="worker-test")

    assert warnings == ["Worker worker-test: schema not migrated yet, skipping this interval"]


@pytest.mark.asyncio
async def test_run_outbox_relay_warns_when_schema_is_not_ready_and_closes_broker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = RecordingBroker()
    closed = {"value": False}

    async def fake_close() -> None:
        closed["value"] = True

    async def fail_relay(received_broker: MessageBroker, worker_id: str, batch_size: int = 20) -> int:
        del received_broker, worker_id, batch_size
        raise DBAPIError("SELECT 1", {}, Exception("relation trip_outbox does not exist"), False)

    async def stop_sleep(seconds: float) -> None:
        del seconds
        raise asyncio.CancelledError

    warnings: list[str] = []

    def fake_warning(message: str, *args) -> None:
        warnings.append(message % args if args else message)

    monkeypatch.setattr(broker, "close", fake_close)
    monkeypatch.setattr("trip_service.workers.outbox_relay._relay_batch", fail_relay)
    monkeypatch.setattr("trip_service.workers.outbox_relay.asyncio.sleep", stop_sleep)
    monkeypatch.setattr(outbox_relay_module.logger, "warning", fake_warning)

    with pytest.raises(asyncio.CancelledError):
        await run_outbox_relay(broker, worker_id="relay-test")

    assert warnings == ["Relay relay-test: schema not migrated yet, skipping this interval"]
    assert closed["value"] is True
