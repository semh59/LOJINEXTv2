import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.conftest import ADMIN_HEADERS, make_manual_trip_payload
from trip_service.broker import MessageBroker, OutboxMessage
from trip_service.models import TripOutbox, TripTrip
from trip_service.workers.outbox_relay import _relay_batch


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


def _gen_26_char_id():
    """Generate a 26-character ID for testing (matches ULID length)."""
    return uuid.uuid4().hex[:26]


@pytest.mark.asyncio
async def test_extreme_parallel_idempotency_contention(client: AsyncClient, db_engine):
    """Stress test: 10 concurrent requests with the same idempotency key."""
    key = f"stress-key-{uuid.uuid4().hex[:8]}"
    payload = make_manual_trip_payload(trip_no=f"TR-STRESS-{key}")
    headers = {**ADMIN_HEADERS, "Idempotency-Key": key}

    # Use a semaphore to spread them but still cause overlap
    sem = asyncio.Semaphore(10)

    async def send_req():
        async with sem:
            return await client.post("/api/v1/trips", json=payload, headers=headers)

    tasks = [send_req() for _ in range(10)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    status_counts = {}
    for r in results:
        if isinstance(r, Exception):
            status_counts["ERROR"] = status_counts.get("ERROR", 0) + 1
            continue
        status_counts[r.status_code] = status_counts.get(r.status_code, 0) + 1

    # At least one MUST succeed with 201 (Original create)
    # Others can be 409 (IN_FLIGHT) or 201 (REPLAY)
    assert status_counts.get(201, 0) >= 1
    # Total successful or blocked should be 10
    assert status_counts.get(201, 0) + status_counts.get(409, 0) == 10

    # CRITICAL: Verify exactly one trip was created in the DB despite many successes (replays)
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        trips = (await session.execute(select(TripTrip).where(TripTrip.trip_no == payload["trip_no"]))).scalars().all()
        assert len(trips) == 1


@pytest.mark.asyncio
async def test_multi_worker_outbox_no_double_processing(db_engine, monkeypatch: pytest.MonkeyPatch):
    """Stress test: Multiple workers trying to process the same batch of outbox messages."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr("trip_service.workers.outbox_relay.async_session_factory", session_factory)

    now = datetime.now(UTC)
    async with session_factory() as session:
        for i in range(50):
            session.add(
                TripOutbox(
                    event_id=_gen_26_char_id(),
                    aggregate_type="TRIP",
                    aggregate_id=f"TRIP-STRESS-{i}",
                    aggregate_version=1,
                    event_name="trip.created.v1",
                    schema_version=1,
                    payload_json="{}",
                    partition_key=f"PART-{i}",
                    publish_status="PENDING",
                    attempt_count=0,
                    created_at_utc=now,
                )
            )
        await session.commit()

    broker = RecordingBroker()

    async def run_worker(worker_id):
        # Multiple workers running with batch size smaller than total
        return await _relay_batch(broker, worker_id=worker_id, batch_size=20)

    worker_results = await asyncio.gather(
        run_worker("worker-1"),
        run_worker("worker-2"),
        run_worker("worker-3"),
    )

    # Total processed across all workers should be exactly 50
    assert sum(worker_results) == 50
    # Broker should have exactly 50 messages (proving no duplicates)
    assert len(broker.messages) == 50
    event_ids = [m.event_id for m in broker.messages]
    assert len(set(event_ids)) == 50


@pytest.mark.asyncio
async def test_stale_claim_recovery_under_load(db_engine, monkeypatch: pytest.MonkeyPatch):
    """Stress test: Stale claim recovery while other workers are processing healthy rows."""
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    monkeypatch.setattr("trip_service.workers.outbox_relay.async_session_factory", session_factory)

    now = datetime.now(UTC)
    async with session_factory() as session:
        for i in range(10):
            session.add(
                TripOutbox(
                    event_id=f"STALE-{i:019d}",
                    aggregate_type="TRIP",
                    aggregate_id=f"T-STALE-{i}",
                    aggregate_version=1,
                    event_name="trip.created.v1",
                    schema_version=1,
                    payload_json="{}",
                    partition_key=f"STALE-{i}",
                    publish_status="PUBLISHING",
                    attempt_count=1,
                    claim_token=f"token-{i}",
                    claim_expires_at_utc=now - timedelta(minutes=10),
                    claimed_by_worker="dead-worker",
                    created_at_utc=now - timedelta(hours=1),
                )
            )
        for i in range(40):
            session.add(
                TripOutbox(
                    event_id=f"FRESH-{i:019d}",
                    aggregate_type="TRIP",
                    aggregate_id=f"T-FRESH-{i}",
                    aggregate_version=1,
                    event_name="trip.created.v1",
                    schema_version=1,
                    payload_json="{}",
                    partition_key=f"FRESH-{i}",
                    publish_status="PENDING",
                    attempt_count=0,
                    created_at_utc=now,
                )
            )
        await session.commit()

    broker = RecordingBroker()
    worker_results = await asyncio.gather(
        _relay_batch(broker, worker_id="worker-A", batch_size=30),
        _relay_batch(broker, worker_id="worker-B", batch_size=30),
    )

    # All 50 (10 recovered + 40 fresh) should be published
    assert sum(worker_results) == 50
    assert len(broker.messages) == 50

    async with session_factory() as session:
        stale_rows = (
            (await session.execute(select(TripOutbox).where(TripOutbox.event_id.like("STALE-%")))).scalars().all()
        )
        assert len(stale_rows) == 10
        assert all(r.publish_status == "PUBLISHED" for r in stale_rows)
