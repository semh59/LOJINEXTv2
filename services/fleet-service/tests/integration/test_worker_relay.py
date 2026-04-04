import datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from fleet_service.broker import NoOpBroker
from fleet_service.config import settings
from fleet_service.models import FleetOutbox
from fleet_service.workers.outbox_relay import _relay_batch


@pytest.mark.asyncio
async def test_relay_batch_success(test_session, test_db_url):
    # 1. Setup outbox records in DB
    # We need to manually insert into FleetOutbox or use repo
    from ulid import ULID

    now = datetime.datetime.now(datetime.timezone.utc)

    outbox_id = str(ULID())
    test_session.add(
        FleetOutbox(
            outbox_id=outbox_id,
            aggregate_type="VEHICLE",
            aggregate_id="v-1",
            event_name="test.event",
            event_version=1,
            payload_json={"id": "v-1"},
            publish_status="PENDING",
            next_attempt_at_utc=now - datetime.timedelta(minutes=1),
            created_at_utc=now,
        )
    )
    await test_session.commit()

    # 2. Run batch relay with mock broker
    mock_broker = AsyncMock(spec=NoOpBroker)

    # We must patch async_session_factory because _relay_batch uses it locally
    with patch("fleet_service.workers.outbox_relay.async_session_factory") as mock_factory:
        # Create a new session for each call to mimic the worker behavior
        engine = create_async_engine(test_db_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        mock_factory.side_effect = session_factory

        published = await _relay_batch(mock_broker, batch_size=10)

    assert published == 1
    mock_broker.publish.assert_called_once()

    # 3. Verify status in DB
    async with session_factory() as session:
        result = await session.execute(select(FleetOutbox).where(FleetOutbox.outbox_id == outbox_id))
        row = result.scalar_one()
        assert row.publish_status == "PUBLISHED"
        assert row.published_at_utc is not None

    await engine.dispose()


@pytest.mark.asyncio
async def test_relay_publish_failure_and_retry(test_session, test_db_url):
    now = datetime.datetime.now(datetime.timezone.utc)
    outbox_id = "01H1234567890ABCDEFGHJKMN2"  # manual id
    test_session.add(
        FleetOutbox(
            outbox_id=outbox_id,
            aggregate_type="VEHICLE",
            aggregate_id="v-2",
            event_name="test.event",
            event_version=1,
            payload_json={"id": "v-2"},
            publish_status="PENDING",
            next_attempt_at_utc=now - datetime.timedelta(minutes=1),
            created_at_utc=now,
            attempt_count=0,
        )
    )
    await test_session.commit()

    # Mock broker that fails
    mock_broker = AsyncMock()
    mock_broker.publish.side_effect = Exception("Broker Connection Failed")

    with patch("fleet_service.workers.outbox_relay.async_session_factory") as mock_factory:
        engine = create_async_engine(test_db_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        mock_factory.side_effect = session_factory

        published = await _relay_batch(mock_broker, batch_size=10)

    assert published == 0

    # Verify status in DB is FAILED with next_attempt_at in future
    async with session_factory() as session:
        result = await session.execute(select(FleetOutbox).where(FleetOutbox.outbox_id == outbox_id))
        row = result.scalar_one()
        assert row.publish_status == "FAILED"
        assert row.attempt_count == 1
        assert row.next_attempt_at_utc > now
        assert row.last_error_code == "PUBLISH_ERROR"

    await engine.dispose()


@pytest.mark.asyncio
async def test_relay_dead_letter_after_max_retries(test_session, test_db_url):
    now = datetime.datetime.now(datetime.timezone.utc)
    outbox_id = "01H1234567890ABCDEFGHJKMN3"

    # Set attempt_count near max
    test_session.add(
        FleetOutbox(
            outbox_id=outbox_id,
            aggregate_type="VEHICLE",
            aggregate_id="v-3",
            event_name="test.event",
            event_version=1,
            payload_json={"id": "v-3"},
            publish_status="PENDING",
            next_attempt_at_utc=now - datetime.timedelta(minutes=1),
            created_at_utc=now,
            attempt_count=settings.outbox_max_retries - 1,  # One more failure and it's dead
        )
    )
    await test_session.commit()

    mock_broker = AsyncMock()
    mock_broker.publish.side_effect = Exception("Permanent Failure")

    with patch("fleet_service.workers.outbox_relay.async_session_factory") as mock_factory:
        engine = create_async_engine(test_db_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        mock_factory.side_effect = session_factory

        await _relay_batch(mock_broker, batch_size=1)

    async with session_factory() as session:
        result = await session.execute(select(FleetOutbox).where(FleetOutbox.outbox_id == outbox_id))
        row = result.scalar_one()
        assert row.publish_status == "DEAD_LETTER"

    await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_relay_safety(test_db_url):
    """
    Simulate two relay workers running concurrently.
    Ensure SKIP LOCKED prevents them from processing the same row.
    """
    engine = create_async_engine(test_db_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # 1. Setup 5 pending rows
    async with session_factory() as session:
        from ulid import ULID

        now = datetime.datetime.now(datetime.timezone.utc)
        for i in range(5):
            session.add(
                FleetOutbox(
                    outbox_id=str(ULID()),
                    aggregate_type="VEHICLE",
                    aggregate_id=f"v-{i}",
                    event_name="test.event",
                    event_version=1,
                    payload_json={"i": i},
                    publish_status="PENDING",
                    next_attempt_at_utc=now - datetime.timedelta(minutes=1),
                    created_at_utc=now,
                )
            )
        await session.commit()

    # 2. Setup mock broker with artificial delay to ensure overlap
    mock_broker = AsyncMock(spec=NoOpBroker)

    async def slow_publish(*args, **kwargs):
        import asyncio

        await asyncio.sleep(0.1)

    mock_broker.publish.side_effect = slow_publish

    # 3. Launch two relay tasks
    with patch("fleet_service.workers.outbox_relay.async_session_factory", side_effect=session_factory):
        import asyncio

        # Run two batches of 5 in parallel
        results = await asyncio.gather(_relay_batch(mock_broker, batch_size=5), _relay_batch(mock_broker, batch_size=5))

    # Total published across both should be 5 (not more!)
    assert sum(results) == 5
    assert mock_broker.publish.call_count == 5

    await engine.dispose()
