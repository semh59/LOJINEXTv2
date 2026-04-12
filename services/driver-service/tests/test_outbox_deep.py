"""Deep testing for Driver Service transactional outbox (V2.1)."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from driver_service.models import DriverModel, DriverOutboxModel
from driver_service.workers.outbox_relay import _process_batch


@pytest.fixture
async def committed_session(engine):
    """Provide a session that actually commits to the DB (no rollback after test)."""
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
async def test_driver(committed_session: AsyncSession):
    """Create a unique dummy driver for each test."""
    from ulid import ULID

    driver_id = str(ULID())  # Exactly 26 chars
    now = datetime.now(timezone.utc)
    driver = DriverModel(
        driver_id=driver_id,
        full_name=f"Test Driver {driver_id}",
        full_name_search_key=f"test driver {driver_id.lower()}",
        license_class="B",
        employment_start_date=now.date(),
        status="ACTIVE",
        created_at_utc=now,
        created_by_actor_id="test-system",
        updated_at_utc=now,
        updated_by_actor_id="test-system",
    )
    committed_session.add(driver)
    await committed_session.commit()
    return driver


@pytest.mark.asyncio
async def test_outbox_stale_claim_recovery(committed_session: AsyncSession, test_driver: DriverModel):
    """Verify that an expired 'PUBLISHING' claim is eventually recovered."""
    now = datetime.now(timezone.utc)

    # 1. Create a stale 'PUBLISHING' entry
    stale_outbox = DriverOutboxModel(
        outbox_id="stale_01",
        driver_id=test_driver.driver_id,
        aggregate_id=test_driver.driver_id,
        event_name="driver.updated",
        payload_json='{"status": "active"}',
        publish_status="PUBLISHING",
        claim_expires_at_utc=now - timedelta(minutes=1),  # Expired
        created_at_utc=now - timedelta(minutes=10),
    )
    committed_session.add(stale_outbox)
    await committed_session.commit()

    # 2. Run relay batch
    mock_broker = AsyncMock()
    published = await _process_batch(committed_session, mock_broker)

    assert published == 1
    mock_broker.publish.assert_called_once()

    # 3. Verify status in DB
    await committed_session.refresh(stale_outbox)
    assert stale_outbox.publish_status == "PUBLISHED"


@pytest.mark.asyncio
async def test_outbox_concurrency_isolation(committed_session: AsyncSession, test_driver: DriverModel):
    """Verify that FOR UPDATE SKIP LOCKED prevents double-publishing."""
    now = datetime.now(timezone.utc)

    # 1. Create multiple pending entries
    for i in range(5):
        committed_session.add(
            DriverOutboxModel(
                outbox_id=f"concurrent_{i}",
                driver_id=test_driver.driver_id,
                aggregate_id=test_driver.driver_id,
                event_name="driver.updated",
                payload_json='{"status": "active"}',
                publish_status="PENDING",
                created_at_utc=now,
            )
        )
    await committed_session.commit()

    mock_broker = AsyncMock()

    from driver_service.database import async_session_factory

    async def run_relay():
        async with async_session_factory() as session:
            return await _process_batch(session, mock_broker)

    # Launching 10 concurrent relay attempts
    tasks = [run_relay() for _ in range(10)]
    results = await asyncio.gather(*tasks)

    total_published = sum(results)
    assert total_published == 5
    assert mock_broker.publish.call_count == 5


@pytest.mark.asyncio
async def test_outbox_broker_failure_retry(committed_session: AsyncSession, test_driver: DriverModel):
    """Verify retry logic and exponential backoff on broker failure."""
    now = datetime.now(timezone.utc)
    outbox = DriverOutboxModel(
        outbox_id="fail_01",
        driver_id=test_driver.driver_id,
        aggregate_id=test_driver.driver_id,
        event_name="driver.updated",
        payload_json='{"status": "active"}',
        publish_status="PENDING",
        created_at_utc=now,
    )
    committed_session.add(outbox)
    await committed_session.commit()

    # 1. Mock broker to fail
    mock_broker = AsyncMock()
    mock_broker.publish.side_effect = Exception("Kafka connection lost")

    # 2. Run relay
    await _process_batch(committed_session, mock_broker)

    # 3. Verify retry state
    await committed_session.refresh(outbox)
    assert outbox.publish_status == "FAILED"
    assert outbox.attempt_count == 1
    assert outbox.last_error == "Kafka connection lost"


@pytest.mark.asyncio
async def test_outbox_dead_letter_transition(committed_session: AsyncSession, test_driver: DriverModel):
    """Verify transition to DEAD_LETTER after max retries."""
    from driver_service.config import settings

    now = datetime.now(timezone.utc)
    outbox = DriverOutboxModel(
        outbox_id="dlq_01",
        driver_id=test_driver.driver_id,
        aggregate_id=test_driver.driver_id,
        event_name="driver.updated",
        payload_json='{"status": "active"}',
        publish_status="FAILED",
        attempt_count=settings.outbox_retry_max - 1,
        created_at_utc=now,
    )
    committed_session.add(outbox)
    await committed_session.commit()

    # 1. Mock broker to fail one last time
    mock_broker = AsyncMock()
    mock_broker.publish.side_effect = Exception("Permanent failure")

    # 2. Run relay
    await _process_batch(committed_session, mock_broker)

    # 3. Verify DEAD_LETTER
    await committed_session.refresh(outbox)
    assert outbox.publish_status == "DEAD_LETTER"
    assert outbox.attempt_count == settings.outbox_retry_max
