"""Abstract message broker interface and implementations.

V8 Section 14: The broker MUST be injectable/abstract, never hardcoded to
a specific technology (Kafka, RabbitMQ, etc.).
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass

logger = logging.getLogger("trip_service.broker")


@dataclass
class OutboxMessage:
    """Message to be published via the broker."""

    event_id: str
    event_name: str
    partition_key: str
    payload: str  # JSON string
    schema_version: int
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


class LogBroker(MessageBroker):
    """Development-only broker that logs messages instead of publishing.

    Suitable for local development. Always succeeds.
    """

    async def publish(self, message: OutboxMessage) -> None:
        """Log the message as published."""
        logger.info(
            "BROKER PUBLISH: event_id=%s event=%s partition=%s aggregate=%s/%s",
            message.event_id,
            message.event_name,
            message.partition_key,
            message.aggregate_type,
            message.aggregate_id,
        )

    async def close(self) -> None:
        """No-op."""
        pass


class NoOpBroker(MessageBroker):
    """Silent broker that discards all messages. Useful for testing."""

    async def publish(self, message: OutboxMessage) -> None:
        """Silently succeed."""
        pass

    async def close(self) -> None:
        """No-op."""
        pass


def create_broker(broker_type: str = "log") -> MessageBroker:
    """Factory for creating broker instances.

    Args:
        broker_type: "log" (dev), "noop" (test), or future: "kafka", "rabbitmq", etc.
    """
    match broker_type:
        case "log":
            return LogBroker()
        case "noop":
            return NoOpBroker()
        case _:
            raise ValueError(f"Unknown broker type: {broker_type}. Supported: log, noop")
