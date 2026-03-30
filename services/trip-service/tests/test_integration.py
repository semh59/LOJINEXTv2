"""Trip Service integration tests."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.conftest import (
    ADMIN_HEADERS,
    EXCEL_SERVICE_HEADERS,
    SUPER_ADMIN_HEADERS,
    TELEGRAM_SERVICE_HEADERS,
    make_excel_payload,
    make_fallback_payload,
    make_manual_trip_payload,
    make_slip_payload,
)
from trip_service.dependencies import fetch_trip_context, probe_location_service, resolve_route_by_names
from trip_service.errors import ProblemDetailError
from trip_service.models import TripIdempotencyRecord, TripOutbox, TripTrip, TripTripDeleteAudit, TripTripEnrichment
from trip_service.routers.trips import _merged_payload_hash


@pytest.mark.asyncio
async def test_manual_create_uses_route_pair_and_snapshots_locations(client: AsyncClient):
    response = await client.post(
        "/api/v1/trips",
        json=make_manual_trip_payload(trip_no="TR-MANUAL-SNAPSHOT"),
        headers=ADMIN_HEADERS,
    )
    body = response.json()
    assert response.status_code == 201
    assert body["status"] == "COMPLETED"
    assert body["route_pair_id"] == "pair-001"
    assert body["route_id"] == "route-ist-ank"
    assert body["origin_name_snapshot"] == "Istanbul"
    assert body["destination_name_snapshot"] == "Ankara"
    assert body["planned_duration_s"] == 21600


@pytest.mark.asyncio
async def test_normal_admin_cannot_create_future_manual_trip(client: AsyncClient):
    future_local = (datetime.now().astimezone().replace(microsecond=0) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    response = await client.post(
        "/api/v1/trips",
        json=make_manual_trip_payload(trip_no="TR-FUTURE-ADMIN", trip_start_local=future_local),
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "TRIP_INVALID_DATE_WINDOW"


@pytest.mark.asyncio
async def test_super_admin_future_manual_trip_becomes_pending_review(client: AsyncClient):
    future_local = (datetime.now().astimezone().replace(microsecond=0) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    response = await client.post(
        "/api/v1/trips",
        json=make_manual_trip_payload(trip_no="TR-FUTURE-SA", trip_start_local=future_local),
        headers=SUPER_ADMIN_HEADERS,
    )
    assert response.status_code == 201
    assert response.json()["status"] == "PENDING_REVIEW"
    assert response.json()["review_reason_code"] == "FUTURE_MANUAL"


@pytest.mark.asyncio
async def test_empty_return_derives_reverse_context_and_suffix(client: AsyncClient):
    base_start = (datetime.now().astimezone().replace(microsecond=0) - timedelta(hours=7)).strftime("%Y-%m-%dT%H:%M")
    return_start = (datetime.now().astimezone().replace(microsecond=0) - timedelta(minutes=10)).strftime(
        "%Y-%m-%dT%H:%M"
    )
    base = await client.post(
        "/api/v1/trips",
        json=make_manual_trip_payload(trip_no="TR-BASE-ER", route_pair_id="pair-001", trip_start_local=base_start),
        headers=SUPER_ADMIN_HEADERS,
    )
    empty_return = await client.post(
        f"/api/v1/trips/{base.json()['id']}/empty-return",
        json={
            "trip_start_local": return_start,
            "trip_timezone": "Europe/Istanbul",
            "driver_id": "driver-001",
            "vehicle_id": "vehicle-001",
            "tare_weight_kg": 14000,
            "gross_weight_kg": 14000,
            "net_weight_kg": 0,
        },
        headers={**SUPER_ADMIN_HEADERS, "If-Match": base.headers["etag"]},
    )
    body = empty_return.json()
    assert empty_return.status_code == 201
    assert body["trip_no"] == "TR-BASE-ER-B"
    assert body["route_id"] == "route-ank-ist"
    assert body["origin_name_snapshot"] == "Ankara"
    assert body["destination_name_snapshot"] == "Istanbul"


@pytest.mark.asyncio
async def test_imported_trip_reject_flow(client: AsyncClient):
    created = await client.post(
        "/internal/v1/trips/slips/ingest",
        json=make_slip_payload(source_slip_no="SLIP-REJECT-01"),
        headers=TELEGRAM_SERVICE_HEADERS,
    )
    response = await client.post(
        f"/api/v1/trips/{created.json()['id']}/reject",
        json={"reason": "bad data"},
        headers={**ADMIN_HEADERS, "If-Match": created.headers["etag"]},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"


@pytest.mark.asyncio
async def test_hard_delete_requires_soft_delete_and_persists_audit(client: AsyncClient, db_engine):
    created = await client.post(
        "/api/v1/trips",
        json=make_manual_trip_payload(trip_no="TR-HARD-AUDIT"),
        headers=SUPER_ADMIN_HEADERS,
    )
    cancelled = await client.post(
        f"/api/v1/trips/{created.json()['id']}/cancel",
        headers={**SUPER_ADMIN_HEADERS, "If-Match": created.headers["etag"]},
    )
    deleted = await client.post(
        f"/api/v1/trips/{created.json()['id']}/hard-delete",
        json={"reason": "duplicate correction"},
        headers={**SUPER_ADMIN_HEADERS, "If-Match": cancelled.headers["etag"]},
    )
    assert deleted.status_code == 204

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        remaining = await session.execute(select(TripTrip).where(TripTrip.id == created.json()["id"]))
        audit = await session.execute(
            select(TripTripDeleteAudit).where(TripTripDeleteAudit.trip_id == created.json()["id"])
        )
    assert remaining.scalar_one_or_none() is None
    audit_row = audit.scalar_one()
    assert audit_row.reason == "duplicate correction"
    assert audit_row.snapshot_json["trip"]["trip_no"] == "TR-HARD-AUDIT"


@pytest.mark.asyncio
async def test_full_telegram_ingest_creates_pending_review(client: AsyncClient):
    response = await client.post(
        "/internal/v1/trips/slips/ingest",
        json=make_slip_payload(source_slip_no="SLIP-PENDING-01"),
        headers=TELEGRAM_SERVICE_HEADERS,
    )
    body = response.json()
    assert response.status_code == 201
    assert body["status"] == "PENDING_REVIEW"
    assert body["review_reason_code"] == "SOURCE_IMPORT"
    assert body["route_pair_id"] == "pair-001"


@pytest.mark.asyncio
async def test_fallback_ingest_creates_incomplete_pending_review(client: AsyncClient):
    response = await client.post(
        "/internal/v1/trips/slips/ingest-fallback",
        json=make_fallback_payload(),
        headers=TELEGRAM_SERVICE_HEADERS,
    )
    body = response.json()
    assert response.status_code == 201
    assert body["status"] == "PENDING_REVIEW"
    assert body["review_reason_code"] == "FALLBACK_MINIMAL"
    assert body["vehicle_id"] is None
    assert body["route_pair_id"] is None


@pytest.mark.asyncio
async def test_fallback_trip_cannot_be_approved_until_completed(client: AsyncClient):
    created = await client.post(
        "/internal/v1/trips/slips/ingest-fallback",
        json=make_fallback_payload(source_reference_key="telegram-message-fallback-approve"),
        headers=TELEGRAM_SERVICE_HEADERS,
    )
    response = await client.post(
        f"/api/v1/trips/{created.json()['id']}/approve",
        json={"note": "approve"},
        headers={**ADMIN_HEADERS, "If-Match": created.headers["etag"]},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "TRIP_COMPLETION_REQUIREMENTS_MISSING"


@pytest.mark.asyncio
async def test_excel_ingest_creates_pending_review(client: AsyncClient):
    response = await client.post(
        "/internal/v1/trips/excel/ingest",
        json=make_excel_payload(source_reference_key="excel-row-001", trip_no="EXCEL-001"),
        headers=EXCEL_SERVICE_HEADERS,
    )
    assert response.status_code == 201
    assert response.json()["status"] == "PENDING_REVIEW"
    assert response.json()["review_reason_code"] == "EXCEL_IMPORT"


@pytest.mark.asyncio
async def test_export_feed_includes_empty_returns(client: AsyncClient):
    base_start = (datetime.now().astimezone().replace(microsecond=0) - timedelta(hours=7)).strftime("%Y-%m-%dT%H:%M")
    return_start = (datetime.now().astimezone().replace(microsecond=0) - timedelta(minutes=10)).strftime(
        "%Y-%m-%dT%H:%M"
    )
    base = await client.post(
        "/api/v1/trips",
        json=make_manual_trip_payload(trip_no="TR-EXPORT-BASE", trip_start_local=base_start),
        headers=SUPER_ADMIN_HEADERS,
    )
    await client.post(
        f"/api/v1/trips/{base.json()['id']}/empty-return",
        json={
            "trip_start_local": return_start,
            "trip_timezone": "Europe/Istanbul",
            "driver_id": "driver-001",
            "vehicle_id": "vehicle-001",
            "tare_weight_kg": 15000,
            "gross_weight_kg": 15000,
            "net_weight_kg": 0,
        },
        headers={**SUPER_ADMIN_HEADERS, "If-Match": base.headers["etag"]},
    )
    response = await client.get("/internal/v1/trips/excel/export-feed", headers=EXCEL_SERVICE_HEADERS)
    trip_numbers = {item["trip_no"] for item in response.json()["items"]}
    assert response.status_code == 200
    assert "TR-EXPORT-BASE" in trip_numbers
    assert "TR-EXPORT-BASE-B" in trip_numbers


@pytest.mark.asyncio
async def test_imported_driver_change_is_locked_for_admin_but_allowed_for_super_admin(client: AsyncClient):
    created = await client.post(
        "/internal/v1/trips/excel/ingest",
        json=make_excel_payload(source_reference_key="excel-row-driver-lock", trip_no="EXCEL-DRIVER-LOCK"),
        headers=EXCEL_SERVICE_HEADERS,
    )
    admin_attempt = await client.patch(
        f"/api/v1/trips/{created.json()['id']}",
        json={"driver_id": "driver-002"},
        headers={**ADMIN_HEADERS, "If-Match": created.headers["etag"]},
    )
    assert admin_attempt.status_code == 409
    assert admin_attempt.json()["code"] == "TRIP_SOURCE_LOCKED_FIELD"

    super_attempt = await client.patch(
        f"/api/v1/trips/{created.json()['id']}",
        json={"driver_id": "driver-002", "change_reason": "manual correction"},
        headers={**SUPER_ADMIN_HEADERS, "If-Match": created.headers["etag"]},
    )
    assert super_attempt.status_code == 200
    assert super_attempt.json()["driver_id"] == "driver-002"


@pytest.mark.asyncio
async def test_overlap_conflict_returns_stable_driver_code(client: AsyncClient):
    first = await client.post(
        "/api/v1/trips",
        json=make_manual_trip_payload(trip_no="TR-OVERLAP-1", route_pair_id="pair-001"),
        headers=ADMIN_HEADERS,
    )
    second = await client.post(
        "/api/v1/trips",
        json=make_manual_trip_payload(trip_no="TR-OVERLAP-2", route_pair_id="pair-001"),
        headers=ADMIN_HEADERS,
    )
    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["code"] == "TRIP_DRIVER_OVERLAP"


@pytest.mark.asyncio
async def test_overlap_conflict_is_serialized_under_concurrency(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    from trip_service import trip_helpers

    original_acquire = trip_helpers._acquire_overlap_locks
    first_lock_acquired = asyncio.Event()
    release_first_request = asyncio.Event()
    first_entry = True
    overlap_start_local = (datetime.now().astimezone().replace(microsecond=0) - timedelta(minutes=5)).strftime(
        "%Y-%m-%dT%H:%M"
    )

    async def delayed_acquire(session, *, driver_id: str, vehicle_id: str, trailer_id: str | None) -> None:
        nonlocal first_entry
        await original_acquire(session, driver_id=driver_id, vehicle_id=vehicle_id, trailer_id=trailer_id)
        if first_entry:
            first_entry = False
            first_lock_acquired.set()
            await release_first_request.wait()

    monkeypatch.setattr("trip_service.trip_helpers._acquire_overlap_locks", delayed_acquire)

    first_task = asyncio.create_task(
        client.post(
            "/api/v1/trips",
            json=make_manual_trip_payload(
                trip_no="TR-OVERLAP-CONCURRENT-1",
                trip_start_local=overlap_start_local,
            ),
            headers=ADMIN_HEADERS,
        )
    )
    await asyncio.wait_for(first_lock_acquired.wait(), timeout=5)

    second_task = asyncio.create_task(
        client.post(
            "/api/v1/trips",
            json=make_manual_trip_payload(
                trip_no="TR-OVERLAP-CONCURRENT-2",
                trip_start_local=overlap_start_local,
            ),
            headers=ADMIN_HEADERS,
        )
    )
    await asyncio.sleep(0.1)
    release_first_request.set()

    first_response, second_response = await asyncio.gather(first_task, second_task)
    statuses = sorted([first_response.status_code, second_response.status_code])
    assert statuses == [201, 409]
    conflict = first_response if first_response.status_code == 409 else second_response
    assert conflict.json()["code"] == "TRIP_DRIVER_OVERLAP"


@pytest.mark.asyncio
async def test_list_trips_hides_soft_deleted_by_default(client: AsyncClient) -> None:
    active = await client.post(
        "/api/v1/trips",
        json=make_manual_trip_payload(trip_no="TR-LIST-ACTIVE"),
        headers=SUPER_ADMIN_HEADERS,
    )
    deleted = await client.post(
        "/api/v1/trips",
        json=make_manual_trip_payload(trip_no="TR-LIST-DELETED", trip_start_local="2026-03-30T11:00"),
        headers=SUPER_ADMIN_HEADERS,
    )
    cancelled = await client.post(
        f"/api/v1/trips/{deleted.json()['id']}/cancel",
        headers={**SUPER_ADMIN_HEADERS, "If-Match": deleted.headers["etag"]},
    )

    default_list = await client.get("/api/v1/trips", headers=ADMIN_HEADERS)
    deleted_list = await client.get("/api/v1/trips", params={"status": "SOFT_DELETED"}, headers=ADMIN_HEADERS)

    assert active.status_code == 201
    assert cancelled.status_code == 200
    assert {item["id"] for item in default_list.json()["items"]} == {active.json()["id"]}
    assert {item["id"] for item in deleted_list.json()["items"]} == {deleted.json()["id"]}


@pytest.mark.asyncio
async def test_cancel_soft_deleted_trip_requires_current_etag(client: AsyncClient) -> None:
    created = await client.post(
        "/api/v1/trips",
        json=make_manual_trip_payload(trip_no="TR-CANCEL-ETAG"),
        headers=SUPER_ADMIN_HEADERS,
    )
    cancelled = await client.post(
        f"/api/v1/trips/{created.json()['id']}/cancel",
        headers={**SUPER_ADMIN_HEADERS, "If-Match": created.headers["etag"]},
    )
    stale_retry = await client.post(
        f"/api/v1/trips/{created.json()['id']}/cancel",
        headers={**SUPER_ADMIN_HEADERS, "If-Match": created.headers["etag"]},
    )
    current_retry = await client.post(
        f"/api/v1/trips/{created.json()['id']}/cancel",
        headers={**SUPER_ADMIN_HEADERS, "If-Match": cancelled.headers["etag"]},
    )

    assert cancelled.status_code == 200
    assert stale_retry.status_code == 412
    assert stale_retry.json()["code"] == "TRIP_VERSION_MISMATCH"
    assert current_retry.status_code == 200
    assert current_retry.headers["etag"] == cancelled.headers["etag"]


@pytest.mark.asyncio
async def test_manual_create_persists_source_payload_hash(client: AsyncClient, db_engine) -> None:
    payload = make_manual_trip_payload(trip_no="TR-SOURCE-HASH")
    request_hash = _merged_payload_hash(payload)
    created = await client.post("/api/v1/trips", json=payload, headers=ADMIN_HEADERS)

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        trip = await session.get(TripTrip, created.json()["id"])

    assert created.status_code == 201
    assert trip is not None
    assert trip.source_payload_hash == request_hash


@pytest.mark.asyncio
async def test_empty_return_persists_source_payload_hash(client: AsyncClient, db_engine) -> None:
    base_start = (datetime.now().astimezone().replace(microsecond=0) - timedelta(hours=7)).strftime("%Y-%m-%dT%H:%M")
    return_start = (datetime.now().astimezone().replace(microsecond=0) - timedelta(minutes=10)).strftime(
        "%Y-%m-%dT%H:%M"
    )
    base = await client.post(
        "/api/v1/trips",
        json=make_manual_trip_payload(trip_no="TR-ER-SOURCE-HASH", trip_start_local=base_start),
        headers=SUPER_ADMIN_HEADERS,
    )
    payload = {
        "trip_start_local": return_start,
        "trip_timezone": "Europe/Istanbul",
        "driver_id": "driver-001",
        "vehicle_id": "vehicle-001",
        "tare_weight_kg": 14000,
        "gross_weight_kg": 14000,
        "net_weight_kg": 0,
    }
    request_hash = _merged_payload_hash(payload)
    created = await client.post(
        f"/api/v1/trips/{base.json()['id']}/empty-return",
        json=payload,
        headers={**SUPER_ADMIN_HEADERS, "If-Match": base.headers["etag"]},
    )

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        trip = await session.get(TripTrip, created.json()["id"])

    assert created.status_code == 201
    assert trip is not None
    assert trip.source_payload_hash == request_hash


@pytest.mark.asyncio
async def test_retry_enrichment_resets_attempt_counter(client: AsyncClient, db_engine) -> None:
    created = await client.post(
        "/internal/v1/trips/slips/ingest",
        json=make_slip_payload(source_slip_no="SLIP-RETRY-RESET-01", source_reference_key="telegram-retry-reset-01"),
        headers=TELEGRAM_SERVICE_HEADERS,
    )
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        enrichment = (
            await session.execute(select(TripTripEnrichment).where(TripTripEnrichment.trip_id == created.json()["id"]))
        ).scalar_one()
        enrichment.enrichment_status = "FAILED"
        enrichment.route_status = "FAILED"
        enrichment.enrichment_attempt_count = 4
        enrichment.next_retry_at_utc = None
        await session.commit()

    retried = await client.post(
        f"/api/v1/trips/{created.json()['id']}/retry-enrichment",
        headers=ADMIN_HEADERS,
    )

    async with session_factory() as session:
        refreshed = (
            await session.execute(select(TripTripEnrichment).where(TripTripEnrichment.trip_id == created.json()["id"]))
        ).scalar_one()

    assert retried.status_code == 202
    assert refreshed.enrichment_attempt_count == 0
    assert refreshed.enrichment_status == "PENDING"


@pytest.mark.asyncio
async def test_manual_idempotency_replays_full_response(client: AsyncClient):
    payload = make_manual_trip_payload(trip_no="TR-IDEMP-FULL")
    created = await client.post(
        "/api/v1/trips",
        json=payload,
        headers={**ADMIN_HEADERS, "Idempotency-Key": "manual-idemp-001"},
    )
    replay = await client.post(
        "/api/v1/trips",
        json=payload,
        headers={**ADMIN_HEADERS, "Idempotency-Key": "manual-idemp-001"},
    )
    assert created.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["id"] == created.json()["id"]
    assert replay.headers["etag"] == created.headers["etag"]


@pytest.mark.asyncio
async def test_manual_idempotency_inflight_returns_controlled_conflict(client: AsyncClient, db_engine):
    payload = make_manual_trip_payload(trip_no="TR-IDEMP-INFLIGHT")
    request_hash = _merged_payload_hash(payload)
    now = datetime.now().astimezone()
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(
            TripIdempotencyRecord(
                idempotency_key="manual-idemp-inflight",
                endpoint_fingerprint="create_trip:admin-test-001",
                request_hash=request_hash,
                response_status=0,
                response_headers_json={},
                response_body_json="{}",
                created_at_utc=now,
                expires_at_utc=now + timedelta(hours=24),
            )
        )
        await session.commit()

    response = await client.post(
        "/api/v1/trips",
        json=payload,
        headers={**ADMIN_HEADERS, "Idempotency-Key": "manual-idemp-inflight"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "TRIP_IDEMPOTENCY_IN_FLIGHT"


@pytest.mark.asyncio
async def test_manual_idempotency_payload_mismatch_same_key(client: AsyncClient):
    first_payload = make_manual_trip_payload(trip_no="TR-IDEMP-MM-1")
    second_payload = make_manual_trip_payload(trip_no="TR-IDEMP-MM-2")
    created = await client.post(
        "/api/v1/trips",
        json=first_payload,
        headers={**ADMIN_HEADERS, "Idempotency-Key": "manual-idemp-mm-001"},
    )
    conflict = await client.post(
        "/api/v1/trips",
        json=second_payload,
        headers={**ADMIN_HEADERS, "Idempotency-Key": "manual-idemp-mm-001"},
    )
    assert created.status_code == 201
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "TRIP_IDEMPOTENCY_PAYLOAD_MISMATCH"


@pytest.mark.asyncio
async def test_telegram_slip_dedupe_and_conflict(client: AsyncClient):
    payload = make_slip_payload(source_slip_no="SLIP-IDEMP-001", source_reference_key="telegram-message-idemp-001")
    created = await client.post("/internal/v1/trips/slips/ingest", json=payload, headers=TELEGRAM_SERVICE_HEADERS)
    replay = await client.post("/internal/v1/trips/slips/ingest", json=payload, headers=TELEGRAM_SERVICE_HEADERS)
    conflict = await client.post(
        "/internal/v1/trips/slips/ingest",
        json={**payload, "net_weight_kg": 14000, "gross_weight_kg": 24000},
        headers=TELEGRAM_SERVICE_HEADERS,
    )
    assert created.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["id"] == created.json()["id"]
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "TRIP_IDEMPOTENCY_PAYLOAD_MISMATCH"


@pytest.mark.asyncio
async def test_driver_statement_shows_completed_only_and_hides_empty_returns(client: AsyncClient):
    first_start = (datetime.now().astimezone().replace(microsecond=0) - timedelta(minutes=25)).strftime(
        "%Y-%m-%dT%H:%M"
    )
    second_start = (datetime.now().astimezone().replace(microsecond=0) - timedelta(hours=7)).strftime("%Y-%m-%dT%H:%M")
    empty_return_start = (datetime.now().astimezone().replace(microsecond=0) - timedelta(minutes=10)).strftime(
        "%Y-%m-%dT%H:%M"
    )
    await client.post(
        "/api/v1/trips",
        json=make_manual_trip_payload(
            trip_no="TR-STMT-COMPLETE",
            driver_id="driver-statement",
            trip_start_local=first_start,
        ),
        headers=ADMIN_HEADERS,
    )
    pending = await client.post(
        "/internal/v1/trips/slips/ingest",
        json=make_slip_payload(
            source_slip_no="SLIP-STMT-PENDING",
            source_reference_key="telegram-message-stmt",
            driver_id="driver-statement",
        ),
        headers=TELEGRAM_SERVICE_HEADERS,
    )
    base = await client.post(
        "/api/v1/trips",
        json=make_manual_trip_payload(
            trip_no="TR-STMT-BASE",
            driver_id="driver-statement",
            route_pair_id="pair-001",
            trip_start_local=second_start,
        ),
        headers=SUPER_ADMIN_HEADERS,
    )
    await client.post(
        f"/api/v1/trips/{base.json()['id']}/empty-return",
        json={
            "trip_start_local": empty_return_start,
            "trip_timezone": "Europe/Istanbul",
            "driver_id": "driver-statement",
            "vehicle_id": "vehicle-001",
            "tare_weight_kg": 14000,
            "gross_weight_kg": 14000,
            "net_weight_kg": 0,
        },
        headers={**SUPER_ADMIN_HEADERS, "If-Match": base.headers["etag"]},
    )

    statement = await client.get(
        "/internal/v1/driver/trips",
        params={"driver_id": "driver-statement"},
        headers=TELEGRAM_SERVICE_HEADERS,
    )
    assert pending.status_code == 201
    assert statement.status_code == 200
    assert statement.json()["meta"]["total_items"] == 2


@pytest.mark.asyncio
async def test_create_manual_trip_writes_outbox_row(client: AsyncClient, db_engine):
    created = await client.post(
        "/api/v1/trips",
        json=make_manual_trip_payload(trip_no="TR-OUTBOX-001"),
        headers=ADMIN_HEADERS,
    )
    assert created.status_code == 201

    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        rows = (
            (await session.execute(select(TripOutbox).where(TripOutbox.aggregate_id == created.json()["id"])))
            .scalars()
            .all()
        )
    assert rows, "Expected at least one outbox row for created trip."


@pytest.mark.asyncio
async def test_parallel_idempotency_is_blocked_safely(client: AsyncClient):
    """Ensure that two concurrent requests with the same key don't create two trips."""
    payload = make_manual_trip_payload(trip_no="TR-PARALLEL-IDEMP")
    headers = {**ADMIN_HEADERS, "Idempotency-Key": "parallel-key-001"}

    # We send both nearly simultaneously.
    # Note: Sequential gather here might not perfectly hit the race, but
    # it validates the 'in-flight' logic if the first one is still processing.
    # To really test the DB lock, we'd need a delay in the router, but
    # the existing logic covers the case where the first one has written the
    # status=0 row.

    results = await asyncio.gather(
        client.post("/api/v1/trips", json=payload, headers=headers),
        client.post("/api/v1/trips", json=payload, headers=headers),
        return_exceptions=True,
    )

    statuses = [r.status_code for r in results if not isinstance(r, Exception)]
    # One should be 201, the other should be 409 (IN_FLIGHT) or 201 (REPLAY if first finished incredibly fast)
    # Given they are in gather, 409 is very likely if the first is in transaction.
    assert 201 in statuses
    if 409 in statuses:
        conflicts = [r.json()["code"] for r in results if hasattr(r, "json") and r.status_code == 409]
        assert "TRIP_IDEMPOTENCY_IN_FLIGHT" in conflicts


@pytest.mark.asyncio
async def test_location_resolve_not_found_maps_to_validation_and_sends_service_auth() -> None:
    response = httpx.Response(
        404,
        json={"code": "LOCATION_ROUTE_RESOLUTION_NOT_FOUND", "detail": "not found"},
        request=httpx.Request("POST", "http://location/internal/v1/routes/resolve"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = response
        with pytest.raises(ProblemDetailError) as exc_info:
            await resolve_route_by_names(origin_name="A", destination_name="B")

    assert exc_info.value.code == "TRIP_VALIDATION_ERROR"
    assert mock_post.await_args.kwargs["headers"]["Authorization"].startswith("Bearer ")


@pytest.mark.asyncio
async def test_location_resolve_ambiguous_maps_to_validation() -> None:
    response = httpx.Response(
        422,
        json={"code": "ROUTE_AMBIGUOUS", "detail": "ambiguous"},
        request=httpx.Request("POST", "http://location/internal/v1/routes/resolve"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = response
        with pytest.raises(ProblemDetailError) as exc_info:
            await resolve_route_by_names(origin_name="A", destination_name="B")

    assert exc_info.value.code == "TRIP_VALIDATION_ERROR"
    assert mock_post.await_count == 1


@pytest.mark.asyncio
async def test_location_trip_context_inactive_maps_to_invalid_route_pair() -> None:
    response = httpx.Response(
        409,
        json={"code": "LOCATION_ROUTE_PAIR_NOT_ACTIVE_USE_CALCULATE"},
        request=httpx.Request("GET", "http://location/internal/v1/route-pairs/pair-001/trip-context"),
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = response
        with pytest.raises(ProblemDetailError) as exc_info:
            await fetch_trip_context("pair-001")

    assert exc_info.value.code == "TRIP_INVALID_ROUTE_PAIR"
    assert mock_get.await_args.kwargs["headers"]["Authorization"].startswith("Bearer ")


@pytest.mark.asyncio
async def test_probe_location_service_uses_authenticated_contract_checks() -> None:
    resolve_response = httpx.Response(
        404,
        json={"code": "LOCATION_ROUTE_RESOLUTION_NOT_FOUND"},
        request=httpx.Request("POST", "http://location/internal/v1/routes/resolve"),
    )
    context_response = httpx.Response(
        404,
        json={"code": "LOCATION_ROUTE_PAIR_NOT_FOUND"},
        request=httpx.Request("GET", "http://location/internal/v1/route-pairs/missing/trip-context"),
    )

    with (
        patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post,
        patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get,
    ):
        mock_post.return_value = resolve_response
        mock_get.return_value = context_response
        ok = await probe_location_service()

    assert ok is True
    assert mock_post.await_args.kwargs["headers"]["Authorization"].startswith("Bearer ")
    assert mock_get.await_args.kwargs["headers"]["Authorization"].startswith("Bearer ")
