"""Trip Service integration tests."""

from __future__ import annotations

from datetime import datetime, timedelta

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
from trip_service.models import TripTrip, TripTripDeleteAudit


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
    return_start = (
        datetime.now().astimezone().replace(microsecond=0) - timedelta(minutes=10)
    ).strftime("%Y-%m-%dT%H:%M")
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
    return_start = (
        datetime.now().astimezone().replace(microsecond=0) - timedelta(minutes=10)
    ).strftime("%Y-%m-%dT%H:%M")
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
    first_start = (
        datetime.now().astimezone().replace(microsecond=0) - timedelta(minutes=25)
    ).strftime("%Y-%m-%dT%H:%M")
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
