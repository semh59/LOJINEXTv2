import pytest
import yaml
from uuid import uuid4
from datetime import UTC, datetime

from trip_service.saga import TripBookingSagaOrchestrator
from trip_service.models import TripOutbox
from trip_service.broker import OutboxMessage


def test_keda_scaledobject_validity():
    """Verify KEDA ScaledObject syntax and query logic."""
    with open("k8s/base/keda-scaledobject.yaml", "r") as f:
        manifest = yaml.safe_load(f)

    assert manifest["kind"] == "ScaledObject"
    assert manifest["spec"]["scaleTargetRef"]["name"] == "trip-outbox-worker"
    trigger = manifest["spec"]["triggers"][0]
    assert trigger["type"] == "postgresql"
    query = trigger["metadata"]["query"]
    assert "trip_outbox" in query
    assert "publish_status" in query


@pytest.mark.asyncio
async def test_saga_causation_trace_propagation(test_session, db_engine, monkeypatch: pytest.MonkeyPatch):
    """Verify that saga compensations correctly propagate causation_id to the broker/outbox."""
    from sqlalchemy.ext.asyncio import async_sessionmaker
    import trip_service.saga as saga_module

    async def mock_get_redis():
        return AsyncMockRedis()

    monkeypatch.setattr("trip_service.saga.get_redis", mock_get_redis)

    class AsyncMockRedis:
        def __init__(self):
            self.data = {}

        async def hset(self, key, field, value):
            if key not in self.data:
                self.data[key] = {}
            self.data[key][field] = value

        def pipeline(self, transaction=True):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        def expire(self, key, seconds):
            pass

        async def execute(self):
            pass

    # We need to mock the broker to inspect the outbox messages
    class MockBroker:
        def __init__(self):
            self.messages = []

        async def publish(self, message: OutboxMessage) -> None:
            self.messages.append(message)

        async def close(self) -> None:
            pass

        async def check_health(self) -> None:
            pass

    mock_broker = MockBroker()
    monkeypatch.setattr("trip_service.saga.create_broker", lambda x: mock_broker)

    # Establish a correlation context with an active causation_id
    from trip_service.observability import causation_id

    initial_causation = f"causation-{uuid4().hex[:8]}"
    token = causation_id.set(initial_causation)

    try:
        saga = TripBookingSagaOrchestrator(trip_id="trip-saga-001")
        # Trigger compensation
        await saga.compensate(reason="customer canceled")

        assert len(mock_broker.messages) == 3  # 3 steps: vehicle, driver, failed

        for msg in mock_broker.messages:
            assert msg.causation_id == initial_causation, f"Message {msg.event_name} did not propagate causation_id"
            assert msg.aggregate_id == "trip-saga-001"

    finally:
        causation_id.reset(token)
