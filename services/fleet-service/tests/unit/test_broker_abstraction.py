import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fleet_service.broker import KafkaBroker, LogBroker, NoOpBroker, OutboxMessage


@pytest.fixture
def outbox_msg():
    return OutboxMessage(
        event_id="evt-123",
        event_name="test.event.v1",
        partition_key="agg-123",
        payload={"data": "test"},
        event_version=1,
        aggregate_type="VEHICLE",
        aggregate_id="agg-123",
    )


@pytest.mark.asyncio
async def test_log_broker_publish(outbox_msg, caplog):
    broker = LogBroker()
    with caplog.at_level("INFO"):
        await broker.publish(outbox_msg)
    assert "BROKER PUBLISH" in caplog.text
    assert "evt-123" in caplog.text


@pytest.mark.asyncio
async def test_noop_broker_publish(outbox_msg):
    broker = NoOpBroker()
    await broker.publish(outbox_msg)  # Should not raise


@pytest.mark.asyncio
async def test_kafka_broker_publish_success(outbox_msg):
    # Mock AIOProducer and AdminClient since they might not be installed in test env
    # or we don't want to connect to a real Kafka.
    mock_producer = MagicMock()
    mock_producer.produce = AsyncMock(return_value=AsyncMock())  # Returns a delivery future

    mock_admin = MagicMock()

    with (
        patch("fleet_service.broker.AIOProducer", return_value=mock_producer),
        patch("fleet_service.broker.AdminClient", return_value=mock_admin),
    ):
        broker = KafkaBroker(producer_config={"bootstrap.servers": "localhost:9092"}, topic="fleet-events")
        await broker.publish(outbox_msg)

        # Verify produce call
        mock_producer.produce.assert_called_once()
        args, kwargs = mock_producer.produce.call_args
        assert args[0] == "fleet-events"
        assert kwargs["key"] == b"agg-123"
        assert kwargs["value"] == json.dumps(outbox_msg.payload).encode("utf-8")


@pytest.mark.asyncio
async def test_kafka_broker_close(outbox_msg):
    mock_producer = MagicMock()
    mock_producer.flush = AsyncMock()
    mock_producer.close = AsyncMock()
    mock_admin = MagicMock()

    with (
        patch("fleet_service.broker.AIOProducer", return_value=mock_producer),
        patch("fleet_service.broker.AdminClient", return_value=mock_admin),
    ):
        broker = KafkaBroker(producer_config={}, topic="test")
        await broker.close()
        mock_producer.flush.assert_called_once()
        mock_producer.close.assert_called_once()
