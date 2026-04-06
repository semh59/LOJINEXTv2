"""Backfill script tests for legacy trip status drift handling."""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from trip_service.models import TripTrip

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "backfill_trip_status_drift.py"
SPEC = importlib.util.spec_from_file_location("trip_backfill_status_drift", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _trip(*, trip_id: str, trip_no: str, source_type: str, status: str) -> TripTrip:
    now = datetime.now(UTC)
    source_reference_key = None
    if source_type in {"TELEGRAM_TRIP_SLIP", "EXCEL_IMPORT"}:
        source_reference_key = f"ref-{trip_id}"
    return TripTrip(
        id=trip_id,
        trip_no=trip_no,
        source_type=source_type,
        source_slip_no=None,
        source_reference_key=source_reference_key,
        source_payload_hash=None,
        review_reason_code=None,
        base_trip_id=None,
        driver_id="driver-001",
        vehicle_id="vehicle-001",
        trailer_id=None,
        route_pair_id="pair-001",
        route_id="route-001",
        origin_location_id="loc-001",
        origin_name_snapshot="Istanbul",
        destination_location_id="loc-002",
        destination_name_snapshot="Ankara",
        trip_datetime_utc=now,
        trip_timezone="Europe/Istanbul",
        planned_duration_s=3600,
        planned_end_utc=now,
        tare_weight_kg=10000,
        gross_weight_kg=25000,
        net_weight_kg=15000,
        is_empty_return=False,
        status=status,
        version=1,
        created_by_actor_type="MANAGER",
        created_by_actor_id="manager-001",
        created_at_utc=now,
        updated_at_utc=now,
        soft_deleted_at_utc=None,
        soft_deleted_by_actor_id=None,
    )


@pytest.mark.asyncio
async def test_backfill_dry_run_reports_blocking_statuses(db_engine) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(
            _trip(
                trip_id="01000000000000000000000000",
                trip_no="TR-REQ",
                source_type="ADMIN_MANUAL",
                status="REQUESTED",
            )
        )
        await session.commit()

    summary = await MODULE.run_backfill(apply=False, session_factory=session_factory)

    assert summary.blocking_rows
    assert summary.blocking_rows[0].status == "REQUESTED"
    assert MODULE.exit_code_for_summary(summary) == 1


@pytest.mark.asyncio
async def test_backfill_apply_converts_cancelled_and_assigned_manual_rows(db_engine) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(
            _trip(
                trip_id="02000000000000000000000000",
                trip_no="TR-CAN",
                source_type="ADMIN_MANUAL",
                status="CANCELLED",
            )
        )
        session.add(
            _trip(
                trip_id="03000000000000000000000000",
                trip_no="TR-ASN",
                source_type="EMPTY_RETURN_ADMIN",
                status="ASSIGNED",
            )
        )
        await session.commit()

    summary = await MODULE.run_backfill(apply=True, session_factory=session_factory)

    assert summary.blocking_rows == []
    assert summary.applied_counts == {"CANCELLED": 1, "ASSIGNED": 1}
    assert summary.remaining_counts == {}
    assert MODULE.exit_code_for_summary(summary) == 0

    async with session_factory() as session:
        cancelled_trip = await session.get(TripTrip, "02000000000000000000000000")
        assigned_trip = await session.get(TripTrip, "03000000000000000000000000")

    assert cancelled_trip is not None and cancelled_trip.status == "SOFT_DELETED"
    assert assigned_trip is not None and assigned_trip.status == "COMPLETED"


@pytest.mark.asyncio
async def test_backfill_dry_run_reports_multiple_blocking_statuses(db_engine) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(
            _trip(
                trip_id="04000000000000000000000000",
                trip_no="TR-REQ-2",
                source_type="ADMIN_MANUAL",
                status="REQUESTED",
            )
        )
        session.add(
            _trip(
                trip_id="05000000000000000000000000",
                trip_no="TR-INPROGRESS",
                source_type="ADMIN_MANUAL",
                status="IN_PROGRESS",
            )
        )
        await session.commit()

    summary = await MODULE.run_backfill(apply=False, session_factory=session_factory)

    assert {row.status for row in summary.blocking_rows} == {"REQUESTED", "IN_PROGRESS"}
    assert MODULE.exit_code_for_summary(summary) == 1


@pytest.mark.asyncio
async def test_backfill_apply_skips_non_convertible_assigned_rows(db_engine) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(
            _trip(
                trip_id="06000000000000000000000000",
                trip_no="TR-ASN-SKIP",
                source_type="TELEGRAM_TRIP_SLIP",
                status="ASSIGNED",
            )
        )
        await session.commit()

    summary = await MODULE.run_backfill(apply=True, session_factory=session_factory)

    assert summary.applied_counts == {"CANCELLED": 0, "ASSIGNED": 0}
    assert summary.remaining_counts == {"ASSIGNED": 1}
    assert MODULE.exit_code_for_summary(summary) == 1


@pytest.mark.asyncio
async def test_backfill_apply_is_idempotent_on_clean_dataset(db_engine) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    summary = await MODULE.run_backfill(apply=True, session_factory=session_factory)

    assert summary.blocking_rows == []
    assert summary.applied_counts == {"CANCELLED": 0, "ASSIGNED": 0}
    assert summary.remaining_counts == {}
    assert MODULE.exit_code_for_summary(summary) == 0


def test_exit_code_for_summary_covers_all_paths() -> None:
    blocking = MODULE.BackfillSummary(
        apply=False,
        blocking_rows=[MODULE.DriftRow(id="trip-1", status="REQUESTED", source_type="ADMIN_MANUAL")],
        planned_counts={},
        applied_counts={},
        remaining_counts={},
    )
    clean_apply = MODULE.BackfillSummary(
        apply=True,
        blocking_rows=[],
        planned_counts={},
        applied_counts={},
        remaining_counts={},
    )
    dirty_apply = MODULE.BackfillSummary(
        apply=True,
        blocking_rows=[],
        planned_counts={},
        applied_counts={},
        remaining_counts={"ASSIGNED": 1},
    )

    assert MODULE.exit_code_for_summary(blocking) == 1
    assert MODULE.exit_code_for_summary(clean_apply) == 0
    assert MODULE.exit_code_for_summary(dirty_apply) == 1
