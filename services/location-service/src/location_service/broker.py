import abc
import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Literal

from location_service.config import settings
from location_service.observability import correlation_id

try:
    from confluent_kafka.admin import AdminClient
except ImportError:
    AdminClient: Any = None  # type: ignore[no-redef]

try:
    from confluent_kafka.aio import AIOProducer
except ImportError:
    try:
        from confluent_kafka.experimental.aio import AIOProducer  # type: ignore[no-redef]
    except ImportError:
        AIOProducer: Any = None  # type: ignore[no-redef]

logger = logging.getLogger("location_service.broker")


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
    causation_id: str | None = None


class EventBroker(abc.ABC):
    """Abstract event broker interface."""

    @abc.abstractmethod
    async def publish(self, message: "OutboxMessage") -> None:
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

    async def probe(self) -> tuple[bool, str | None]:
        """Compatibility method for readiness checks."""
        try:
            await self.check_health()
            return True, None
        except Exception as exc:
            return False, str(exc)


class NoopBroker(EventBroker):
    """Swallows events."""

    async def publish(self, message: "OutboxMessage") -> None:
        pass

    async def close(self) -> None:
        pass

    async def check_health(self) -> None:
        pass


class LogBroker(EventBroker):
    """Logs events to stdout."""

    async def publish(self, message: "OutboxMessage") -> None:
        c_id = correlation_id.get() or "no-correlation-id"
        logger.info(
            "EVENT [%s] correlation_id=%s key=%s payload=%s causation_id=%s",
            message.event_name,
            c_id,
            message.partition_key,
            message.payload,
            message.causation_id,
        )

    async def close(self) -> None:
        pass

    async def check_health(self) -> None:
        pass


class KafkaBroker(EventBroker):
    """Publishes events to Kafka using AIOProducer."""

    def __init__(self, bootstrap_servers: str, client_id: str, **kwargs: object) -> None:
        if AIOProducer is None or AdminClient is None:
            raise RuntimeError("confluent-kafka with asyncio support is not installed.")

        config: dict[str, Any] = {
            "bootstrap.servers": bootstrap_servers,
            "client.id": client_id,
        }
        config.update(kwargs)
        self._producer = AIOProducer(config)
        self._admin = AdminClient(config)

    async def publish(self, message: "OutboxMessage") -> None:
        headers = []
        c_id = correlation_id.get()
        if c_id:
            headers.append(("X-Correlation-ID", c_id.encode()))
        if message.causation_id:
            headers.append(("X-Causation-ID", message.causation_id.encode()))

        delivery_future = await self._producer.produce(
            message.event_name,
            key=message.partition_key.encode(),
            value=message.payload.encode(),
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


def create_broker(
    broker_type: Literal["kafka", "log", "noop"] | None = None,
) -> EventBroker:
    """Factory function to create the appropriate broker."""
    # Location service might not have a BROKER_TYPE settings, so we fallback to Kafka if bootstrap exists
    if broker_type:
        resolved = broker_type
    elif settings.kafka_bootstrap_servers and settings.environment != "dev":
        resolved = "kafka"
    elif settings.environment == "dev":
        resolved = "log"
    else:
        resolved = "noop"

    if resolved == "kafka":
        if AIOProducer is None:
            # confluent-kafka not installed (e.g. test environment) — fall back to log broker
            return LogBroker()
        return KafkaBroker(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            client_id=settings.kafka_client_id,
        )
    if resolved == "log":
        return LogBroker()
    return NoopBroker()
