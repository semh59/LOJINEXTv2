"""Abstract message broker interface and implementations (Section 15).

The broker MUST be injectable/abstract, never hardcoded to a specific technology.
"""

from __future__ import annotations

import abc
import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from fleet_service.config import settings

try:
    from confluent_kafka.admin import AdminClient
except ImportError:  # pragma: no cover
    AdminClient = None

try:
    from confluent_kafka.aio import AIOProducer
except ImportError:  # pragma: no cover
    try:
        from confluent_kafka.experimental.aio import AIOProducer
    except ImportError:  # pragma: no cover
        AIOProducer = None

logger = logging.getLogger("fleet_service.broker")


@dataclass
class OutboxMessage:
    """Message to be published via the broker."""

    event_id: str
    event_name: str
    partition_key: str
    payload: dict[str, Any]
    event_version: int
    aggregate_type: str
    aggregate_id: str


class MessageBroker(abc.ABC):
    """Abstract message broker interface.

    Implementations must handle:
    - Connection management
    - Publishing to the appropriate topic/queue
    - Error reporting (raise on failure)
    """

    @abc.abstractmethod
    async def publish(self, message: OutboxMessage) -> None:
        """Publish a single message. Raises on failure."""
        ...

    @abc.abstractmethod
    async def close(self) -> None:
        """Gracefully close the broker connection."""
        ...

    @abc.abstractmethod
    async def check_health(self) -> None:
        """Raise when the broker is not healthy."""
        ...


class LogBroker(MessageBroker):
    """Development-only broker that logs messages instead of publishing."""

    async def publish(self, message: OutboxMessage) -> None:
        """Log the message as published."""
        logger.info(
            "BROKER PUBLISH: event_id=%s event=%s aggregate=%s/%s",
            message.event_id,
            message.event_name,
            message.aggregate_type,
            message.aggregate_id,
        )

    async def close(self) -> None:
        """No-op."""

    async def check_health(self) -> None:
        """Development log broker is always considered healthy."""


class NoOpBroker(MessageBroker):
    """Silent broker that discards all messages. Useful for testing."""

    async def publish(self, message: OutboxMessage) -> None:
        """Silently succeed."""

    async def close(self) -> None:
        """No-op."""

    async def check_health(self) -> None:
        """Test broker is always considered healthy."""


class KafkaBroker(MessageBroker):
    """Kafka-backed broker using Confluent's asyncio producer."""

    def __init__(self, producer_config: dict[str, str], topic: str) -> None:
        if AIOProducer is None or AdminClient is None:
            raise RuntimeError("confluent-kafka with asyncio support is not installed.")
        self._topic = topic
        self._producer = AIOProducer(producer_config)
        self._admin = AdminClient(producer_config)

    async def publish(self, message: OutboxMessage) -> None:
        """Publish a JSON payload to the configured Kafka topic."""
        delivery_future = await self._producer.produce(
            self._topic,
            key=message.partition_key.encode("utf-8"),
            value=json.dumps(message.payload).encode("utf-8"),
        )
        await delivery_future

    async def close(self) -> None:
        """Flush buffered messages and close the underlying producer."""
        await self._producer.flush()
        await self._producer.close()

    async def check_health(self) -> None:
        """Verify broker connectivity by requesting cluster metadata."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._list_topics)

    def _list_topics(self) -> Any:
        """Synchronously fetch metadata from Kafka for health checks."""
        return self._admin.list_topics(timeout=5)


def _kafka_config() -> dict[str, str]:
    """Build the Confluent Kafka client configuration."""
    config: dict[str, str] = {
        "bootstrap.servers": settings.kafka_bootstrap_servers,
        "client.id": settings.kafka_client_id,
        "security.protocol": settings.kafka_security_protocol,
    }
    if settings.kafka_sasl_mechanism:
        config["sasl.mechanism"] = settings.kafka_sasl_mechanism
    if settings.kafka_sasl_username:
        config["sasl.username"] = settings.kafka_sasl_username
    if settings.kafka_sasl_password:
        config["sasl.password"] = settings.kafka_sasl_password
    return config


def create_broker(broker_type: str) -> MessageBroker:
    """Factory for creating broker instances.

    Args:
        broker_type: "kafka", "log", or "noop".
    """
    match broker_type:
        case "kafka":
            return KafkaBroker(_kafka_config(), settings.kafka_topic)
        case "log":
            return LogBroker()
        case "noop":
            return NoOpBroker()
        case _:
            raise ValueError(f"Unknown broker type: {broker_type}. Supported: kafka, log, noop")
