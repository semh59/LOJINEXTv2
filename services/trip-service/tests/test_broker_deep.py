"""Deep broker and factory coverage for trip-service."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import trip_service.broker as broker_module
from trip_service.broker import KafkaBroker, LogBroker, NoOpBroker, OutboxMessage, create_broker

pytestmark = pytest.mark.runtime


def test_create_broker_factory_covers_supported_and_invalid_types() -> None:
    assert isinstance(create_broker("log"), LogBroker)
    assert isinstance(create_broker("noop"), NoOpBroker)
    with pytest.raises(ValueError, match="Unknown broker type"):
        create_broker("redis")


def test_kafka_config_includes_optional_sasl_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(broker_module.settings, "kafka_bootstrap_servers", "kafka:9092")
    monkeypatch.setattr(broker_module.settings, "kafka_client_id", "trip-service")
    monkeypatch.setattr(broker_module.settings, "kafka_security_protocol", "SASL_SSL")
    monkeypatch.setattr(broker_module.settings, "kafka_sasl_mechanism", "SCRAM-SHA-512")
    monkeypatch.setattr(broker_module.settings, "kafka_sasl_username", "trip-user")
    monkeypatch.setattr(broker_module.settings, "kafka_sasl_password", "trip-pass")

    assert broker_module._kafka_config() == {
        "bootstrap.servers": "kafka:9092",
        "client.id": "trip-service",
        "security.protocol": "SASL_SSL",
        "sasl.mechanism": "SCRAM-SHA-512",
        "sasl.username": "trip-user",
        "sasl.password": "trip-pass",
    }


def test_kafka_broker_init_requires_confluent_async_support(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(broker_module, "AIOProducer", None)
    monkeypatch.setattr(broker_module, "AdminClient", object)

    with pytest.raises(RuntimeError, match="asyncio support"):
        KafkaBroker({"bootstrap.servers": "kafka:9092"}, "trip.events.v1")


@pytest.mark.asyncio
async def test_kafka_broker_publish_and_close_delegate_to_underlying_clients() -> None:
    captured: dict[str, object] = {}

    class FakeProducer:
        async def produce(self, topic: str, *, key: bytes, value: bytes, headers=None):
            captured["topic"] = topic
            captured["key"] = key
            captured["value"] = value
            return asyncio.sleep(0)

        async def flush(self) -> None:
            captured["flushed"] = True

        async def close(self) -> None:
            captured["closed"] = True

    broker = object.__new__(KafkaBroker)
    broker._topic = "trip.events.v1"
    broker._producer = FakeProducer()
    broker._admin = object()

    await broker.publish(
        OutboxMessage(
            event_id="evt-001",
            event_name="trip.created.v1",
            partition_key="trip-001",
            payload='{"trip_id":"trip-001"}',
            schema_version=1,
            aggregate_type="TRIP",
            aggregate_id="trip-001",
        )
    )
    await broker.close()

    assert captured == {
        "topic": "trip.events.v1",
        "key": b"trip-001",
        "value": b'{"trip_id":"trip-001"}',
        "flushed": True,
        "closed": True,
    }


@pytest.mark.asyncio
async def test_kafka_broker_health_uses_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeLoop:
        async def run_in_executor(self, executor, fn):
            captured["executor"] = executor
            captured["result"] = fn()
            return captured["result"]

    broker = object.__new__(KafkaBroker)
    broker._topic = "trip.events.v1"
    broker._producer = object()
    broker._admin = SimpleNamespace(list_topics=lambda timeout: {"timeout": timeout})

    monkeypatch.setattr(broker_module.asyncio, "get_running_loop", lambda: FakeLoop())

    await broker.check_health()

    assert captured["executor"] is None
    assert captured["result"] == {"timeout": broker_module.settings.dependency_timeout_seconds}
