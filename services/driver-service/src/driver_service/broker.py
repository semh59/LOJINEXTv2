"""Event broker abstraction for Driver Service — matching trip-service pattern."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Literal

logger = logging.getLogger("driver_service")


class EventBroker(ABC):
    """Abstract event broker interface."""

    @abstractmethod
    async def publish(self, topic: str, key: str, payload: dict) -> None:
        """Publish an event to the broker."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Clean up broker resources."""
        ...


class NoopBroker(EventBroker):
    """Swallows events — used in tests."""

    async def publish(self, topic: str, key: str, payload: dict) -> None:
        pass

    async def close(self) -> None:
        pass


class LogBroker(EventBroker):
    """Logs events to stdout — used in dev."""

    async def publish(self, topic: str, key: str, payload: dict) -> None:
        logger.info("EVENT [%s] key=%s payload=%s", topic, key, json.dumps(payload))

    async def close(self) -> None:
        pass


class KafkaBroker(EventBroker):
    """Publishes events to Kafka — used in prod."""

    def __init__(self, bootstrap_servers: str, client_id: str, **kwargs: object) -> None:
        from confluent_kafka import Producer

        config: dict[str, object] = {
            "bootstrap.servers": bootstrap_servers,
            "client.id": client_id,
        }
        config.update(kwargs)
        self._producer = Producer(config)

    async def publish(self, topic: str, key: str, payload: dict) -> None:
        self._producer.produce(
            topic,
            key=key.encode(),
            value=json.dumps(payload).encode(),
        )
        self._producer.flush(timeout=5)

    async def close(self) -> None:
        self._producer.flush(timeout=10)


def create_broker(broker_type: Literal["kafka", "log", "noop"]) -> EventBroker:
    """Factory function to create the appropriate broker."""
    if broker_type == "kafka":
        from driver_service.config import settings

        return KafkaBroker(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            client_id=settings.kafka_client_id,
        )
    if broker_type == "log":
        return LogBroker()
    return NoopBroker()
