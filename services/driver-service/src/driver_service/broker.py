"""Event broker abstraction for Driver Service — matching trip-service pattern."""

import abc
import asyncio
import json
import logging
from typing import Any, Literal

from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient

from driver_service.config import settings
from driver_service.observability import correlation_id

AIOProducer = None  # We will use Producer and wrap it if needed, or stick to Producer for reliability

logger = logging.getLogger("driver_service.broker")


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
        pass

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
    """Publishes events to Kafka using standard Producer."""

    def __init__(self, bootstrap_servers: str, client_id: str, **kwargs: object) -> None:
        config: dict[str, object] = {
            "bootstrap.servers": bootstrap_servers,
            "client.id": client_id,
            "acks": "all",
            "enable.idempotence": True,
        }
        config.update(kwargs)
        self._producer = Producer(config)
        self._admin = AdminClient(config)
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def _poll_loop(self) -> None:
        """Background task to continuously poll for delivery reports."""
        try:
            while True:
                # Poll for events (callbacks)
                self._producer.poll(0.1)
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Kafka poll loop error")

    async def publish(self, topic: str, key: str, payload: dict[str, Any]) -> None:
        headers = []
        c_id = correlation_id.get() or payload.get("correlation_id")
        r_id = payload.get("request_id")
        causation_id = payload.get("causation_id")

        if c_id:
            headers.append(("X-Correlation-ID", str(c_id).encode()))
        if r_id:
            headers.append(("X-Request-ID", str(r_id).encode()))
        if causation_id:
            headers.append(("X-Causation-ID", str(causation_id).encode()))

        loop = asyncio.get_running_loop()
        future: asyncio.Future[None] = loop.create_future()

        def delivery_report(err: Any, msg: Any) -> None:
            if err is not None:
                future.set_exception(RuntimeError(f"Kafka delivery failed: {err}"))
            else:
                future.set_result(None)

        self._producer.produce(
            topic,
            key=key.encode(),
            value=json.dumps(payload).encode(),
            headers=headers,
            callback=delivery_report,
        )
        await future

    async def close(self) -> None:
        self._poll_task.cancel()
        try:
            await self._poll_task
        except asyncio.CancelledError:
            pass
        self._producer.flush()

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
