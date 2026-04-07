"""Deep architectural tests for Outbox Relay component."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from location_service.config import settings
from location_service.models import LocationOutboxModel
from location_service.workers.outbox_relay import _process_batch


@pytest.fixture
def override_outbox_settings():
    old_batch = settings.outbox_publish_batch_size
    old_retry = settings.outbox_retry_max
    settings.outbox_publish_batch_size = 10
    settings.outbox_retry_max = 5
    yield
    settings.outbox_publish_batch_size = old_batch
    settings.outbox_retry_max = old_retry


@pytest.mark.asyncio
async def test_outbox_deep_concurrency_isolation(db_engine, override_outbox_settings) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    # Setup data
    async with session_factory() as session:
        for i in range(10):
            session.add(
                LocationOutboxModel(
                    event_name=f"test.event.{i}",
                    payload_json={"target_id": str(uuid.uuid4())},
                    partition_key="key",
                    created_at_utc=datetime.now(UTC),
                    next_attempt_at_utc=datetime.now(UTC),
                )
            )
        await session.commit()

    broker = AsyncMock()

    async def worker_run() -> int:
        async with session_factory() as worker_session:
            return await _process_batch(worker_session, broker)

    # 3 simultaneous workers trying to claim the batch using SKIP_LOCKED
    results = await asyncio.gather(worker_run(), worker_run(), worker_run())

    total_processed = sum(results)
    assert total_processed == 10
    # Because of isolation, exactly 10 calls to publish without duplications
    assert broker.publish.call_count == 10


@pytest.mark.asyncio
async def test_outbox_deep_stale_claim_recovery(db_engine, override_outbox_settings) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        # Row that crashed mid-publish an hour ago
        stale_row = LocationOutboxModel(
            event_name="test.event.stale",
            payload_json={"target_id": "123"},
            partition_key="key",
            publish_status="PUBLISHING",
            claim_expires_at_utc=datetime.now(UTC) - timedelta(minutes=60),
            created_at_utc=datetime.now(UTC) - timedelta(hours=2),
            next_attempt_at_utc=datetime.now(UTC),
        )
        session.add(stale_row)
        await session.commit()

        broker = AsyncMock()
        processed = await _process_batch(session, broker)

        # Should have reclaimed the stale row
        assert processed == 1
        assert broker.publish.call_count == 1

        await session.refresh(stale_row)
        assert stale_row.publish_status == "PUBLISHED"


@pytest.mark.asyncio
async def test_outbox_deep_broker_fault_dlq_backoff(db_engine, override_outbox_settings) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        row = LocationOutboxModel(
            event_name="test.event.dlq",
            payload_json={"target_id": "dlq_test"},
            partition_key="key",
            created_at_utc=datetime.now(UTC),
            next_attempt_at_utc=datetime.now(UTC),
        )
        session.add(row)
        await session.commit()

        class FailingBroker:
            async def publish(self, *args, **kwargs) -> None:
                raise ConnectionError("Kafka is down")

        broker = FailingBroker()

        for i in range(settings.outbox_retry_max):
            # Force eligible for retry
            row.next_attempt_at_utc = datetime.now(UTC) - timedelta(seconds=1)
            session.add(row)
            await session.commit()

            await _process_batch(session, broker)
            await session.refresh(row)

            if i < settings.outbox_retry_max - 1:
                assert row.publish_status == "FAILED"
                assert row.retry_count == i + 1
                assert row.last_error_code == "ConnectionError"
                assert row.next_attempt_at_utc > datetime.now(UTC)  # Backoff
            else:
                assert row.publish_status == "DEAD_LETTER"
                assert row.retry_count == settings.outbox_retry_max


@pytest.mark.asyncio
async def test_outbox_deep_partial_batch_isolation(db_engine, override_outbox_settings) -> None:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        for i in range(3):
            session.add(
                LocationOutboxModel(
                    event_name=f"test.event.{i}",
                    payload_json={"target_id": f"id_{i}"},
                    partition_key="key",
                    created_at_utc=datetime.now(UTC),
                    next_attempt_at_utc=datetime.now(UTC),
                )
            )
        await session.commit()

        class PartialFailingBroker:
            def __init__(self):
                self.successes = 0

            async def publish(self, payload, **kwargs) -> None:
                if payload["aggregate_id"] == "id_1":
                    raise ValueError("Bad payload schema")
                self.successes += 1

        broker = PartialFailingBroker()
        processed = await _process_batch(session, broker)

        # Returns 2 successfully published out of the claimed batch
        assert processed == 2
        assert broker.successes == 2

        result = await session.execute(select(LocationOutboxModel).order_by(LocationOutboxModel.event_name))
        rows = result.scalars().all()

        # Isolation asserts: failure in middle row didn't block or rollback surrounding rows
        assert rows[0].publish_status == "PUBLISHED"
        assert rows[1].publish_status == "FAILED"
        assert rows[1].last_error_code == "ValueError"
        assert rows[2].publish_status == "PUBLISHED"
