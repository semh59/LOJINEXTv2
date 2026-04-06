import abc
import asyncio
import json
import logging
from typing import Any, Literal

from location_service.config import settings
from location_service.observability import correlation_id

try:
    from confluent_kafka.admin import AdminClient
except ImportError:
    AdminClient = None

try:
    from confluent_kafka.aio import AIOProducer
except ImportError:
    try:
        from confluent_kafka.experimental.aio import AIOProducer
    except ImportError:
        AIOProducer = None

logger = logging.getLogger("location_service.broker")


class EventBroker(abc.ABC):
    """Abstract event broker interface."""

    @abc.abstractmethod
    async def publish(self, topic: str, key: str, payload: dict[str, Any]) -> None:
        """Publish an event to the broker."""
        ...

    @abc.abstractmethod
    async def close(self) -> None:
        """Clean up broker resources."""
        ...

    @abc.abstractmethod
    async def check_health(self) -> None:
        """Raise when the broker is not healthy."""
        ...


class NoopBroker(EventBroker):
    """Swallows events."""

    async def publish(self, topic: str, key: str, payload: dict[str, Any]) -> None:
        del topic, key, payload

    async def close(self) -> None:
        pass

    async def check_health(self) -> None:
        pass


class LogBroker(EventBroker):
    """Logs events to stdout."""

    async def publish(self, topic: str, key: str, payload: dict[str, Any]) -> None:
        c_id = correlation_id.get() or "no-correlation-id"
        logger.info("EVENT [%s] correlation_id=%s key=%s payload=%s", topic, c_id, key, json.dumps(payload))

    async def close(self) -> None:
        pass

    async def check_health(self) -> None:
        pass


class KafkaBroker(EventBroker):
    """Publishes events to Kafka using AIOProducer."""

    def __init__(self, bootstrap_servers: str, client_id: str, **kwargs: object) -> None:
        if AIOProducer is None or AdminClient is None:
            raise RuntimeError("confluent-kafka with asyncio support is not installed.")

        config: dict[str, object] = {
            "bootstrap.servers": bootstrap_servers,
            "client.id": client_id,
        }
        config.update(kwargs)
        self._producer = AIOProducer(config)
        self._admin = AdminClient(config)

    async def publish(self, topic: str, key: str, payload: dict[str, Any]) -> None:
        headers = []
        c_id = correlation_id.get()
        if c_id:
            headers.append(("X-Correlation-ID", c_id.encode()))

        delivery_future = await self._producer.produce(
            topic,
            key=key.encode(),
            value=json.dumps(payload).encode(),
            headers=headers,
        )
        await delivery_future

    async def close(self) -> None:
        await self._producer.flush()
        await self._producer.close()

    async def check_health(self) -> None:
        """Verify broker connectivity via AdminClient."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._list_topics)

    def _list_topics(self) -> Any:
        return self._admin.list_topics(timeout=5)


def create_broker(broker_type: Literal["kafka", "log", "noop"]) -> EventBroker:
    """Factory function to create the appropriate broker."""
    if broker_type == "kafka":
        return KafkaBroker(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            client_id=settings.kafka_client_id,
        )
    if broker_type == "log":
        return LogBroker()
    return NoopBroker()
