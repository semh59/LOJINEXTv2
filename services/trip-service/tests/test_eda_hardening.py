from uuid import uuid4

import pytest
import yaml
from trip_service.saga import TripBookingSagaOrchestrator

from trip_service.models import TripOutbox


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

    # No need to mock create_broker anymore as we use the outbox directly

    # Establish a correlation context with an active causation_id
    from trip_service.observability import causation_id

    initial_causation = f"causation-{uuid4().hex[:8]}"
    token = causation_id.set(initial_causation)

    try:
        saga = TripBookingSagaOrchestrator(trip_id="trip-saga-001", session=test_session)
        # Trigger compensation
        await saga.compensate(reason="customer canceled")

        from sqlalchemy import select

        result = await test_session.execute(select(TripOutbox).where(TripOutbox.aggregate_id == "trip-saga-001"))
        messages = result.scalars().all()

        assert len(messages) == 3  # 3 steps: vehicle, driver, failed

        for msg in messages:
            assert msg.causation_id == initial_causation, f"Message {msg.event_name} did not propagate causation_id"
            assert msg.aggregate_id == "trip-saga-001"
            assert "trip_id" in msg.payload_json

    finally:
        causation_id.reset(token)
