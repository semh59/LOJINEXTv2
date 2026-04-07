"""Tests for worker heartbeat write, read, and staleness detection.

Covers location_service.worker_heartbeats — three critical functions used by
the readiness probe (/ready) to determine whether the processing worker is alive.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from location_service.worker_heartbeats import (
    HeartbeatSnapshot,
    get_worker_heartbeat_snapshot,
    read_worker_heartbeat,
    record_worker_heartbeat,
)


# ---------------------------------------------------------------------------
# Fixture: patch async_session_factory for each test
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def heartbeat_session_factory(db_engine, monkeypatch: pytest.MonkeyPatch):
    """Patch worker_heartbeats.async_session_factory to use test DB."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr("location_service.worker_heartbeats.async_session_factory", factory)
    return factory


# ---------------------------------------------------------------------------
# record_worker_heartbeat
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_record_writes_heartbeat_to_db(heartbeat_session_factory) -> None:
    """record_worker_heartbeat persists a timestamp that can be read back."""
    ts = datetime(2026, 4, 7, 10, 0, 0, tzinfo=UTC)
    await record_worker_heartbeat("processing-worker", ts)

    result = await read_worker_heartbeat("processing-worker")
    assert result is not None
    assert result.replace(microsecond=0) == ts.replace(microsecond=0)


@pytest.mark.asyncio
async def test_record_upserts_on_repeated_call(heartbeat_session_factory) -> None:
    """A second record call updates the existing row, not inserts a duplicate."""
    first_ts = datetime(2026, 4, 7, 10, 0, 0, tzinfo=UTC)
    second_ts = datetime(2026, 4, 7, 10, 1, 0, tzinfo=UTC)

    await record_worker_heartbeat("processing-worker", first_ts)
    await record_worker_heartbeat("processing-worker", second_ts)

    result = await read_worker_heartbeat("processing-worker")
    assert result is not None
    assert result.replace(microsecond=0) == second_ts.replace(microsecond=0)


@pytest.mark.asyncio
async def test_record_distinct_workers_are_independent(heartbeat_session_factory) -> None:
    """Different worker names are stored as separate rows."""
    ts_a = datetime(2026, 4, 7, 9, 0, 0, tzinfo=UTC)
    ts_b = datetime(2026, 4, 7, 9, 30, 0, tzinfo=UTC)

    await record_worker_heartbeat("processing-worker", ts_a)
    await record_worker_heartbeat("outbox-relay-worker", ts_b)

    r_a = await read_worker_heartbeat("processing-worker")
    r_b = await read_worker_heartbeat("outbox-relay-worker")

    assert r_a is not None and r_a.replace(microsecond=0) == ts_a.replace(microsecond=0)
    assert r_b is not None and r_b.replace(microsecond=0) == ts_b.replace(microsecond=0)


# ---------------------------------------------------------------------------
# read_worker_heartbeat
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_read_returns_none_for_unknown_worker(heartbeat_session_factory) -> None:
    """read_worker_heartbeat returns None when the worker has never recorded."""
    result = await read_worker_heartbeat("nonexistent-worker")
    assert result is None


# ---------------------------------------------------------------------------
# get_worker_heartbeat_snapshot
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_snapshot_unavailable_when_no_record(heartbeat_session_factory) -> None:
    """Snapshot status is 'unavailable' when the worker has never written."""
    snapshot = await get_worker_heartbeat_snapshot("ghost-worker", stale_after_seconds=60)
    assert isinstance(snapshot, HeartbeatSnapshot)
    assert snapshot.status == "unavailable"
    assert snapshot.recorded_at_utc is None


@pytest.mark.asyncio
async def test_snapshot_ok_for_recent_heartbeat(heartbeat_session_factory) -> None:
    """Snapshot status is 'ok' when heartbeat is within the stale threshold."""
    fresh_ts = datetime.now(UTC) - timedelta(seconds=5)
    await record_worker_heartbeat("processing-worker", fresh_ts)

    snapshot = await get_worker_heartbeat_snapshot("processing-worker", stale_after_seconds=60)
    assert snapshot.status == "ok"
    assert snapshot.recorded_at_utc is not None


@pytest.mark.asyncio
async def test_snapshot_stale_when_heartbeat_exceeds_threshold(heartbeat_session_factory) -> None:
    """Snapshot status is 'stale' when heartbeat is older than stale_after_seconds."""
    old_ts = datetime.now(UTC) - timedelta(seconds=120)
    await record_worker_heartbeat("processing-worker", old_ts)

    snapshot = await get_worker_heartbeat_snapshot("processing-worker", stale_after_seconds=60)
    assert snapshot.status == "stale"
    assert snapshot.recorded_at_utc is not None


@pytest.mark.asyncio
async def test_snapshot_boundary_at_exact_threshold(heartbeat_session_factory) -> None:
    """Snapshot is 'stale' at exactly the threshold (> not >=)."""
    # timedelta comparison is: now - recorded > threshold → stale
    # At exactly threshold seconds ago the comparison is equal (not greater), so → 'ok'
    # One second older → stale
    exactly_stale_ts = datetime.now(UTC) - timedelta(seconds=61)
    await record_worker_heartbeat("processing-worker", exactly_stale_ts)

    snapshot = await get_worker_heartbeat_snapshot("processing-worker", stale_after_seconds=60)
    assert snapshot.status == "stale"
