"""Abstract message broker and canonical OutboxMessage dataclass.

All services MUST use the ``MessageBroker`` ABC and publish via
``OutboxMessage`` for guaranteed header propagation and uniform
serialisation.
"""

from __future__ import annotations

import abc
import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from .context import causation_id as ctx_causation_id, correlation_id as ctx_correlation_id

logger = logging.getLogger("platform_common.broker")


class RobustJSONEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime, date, and Decimal types."""

    def default(self, o: Any) -> Any:
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, Decimal):
            return str(o)
        return super().default(o)


# ---------------------------------------------------------------------------
# AIOProducer import with fallback
# ---------------------------------------------------------------------------
try:
    from confluent_kafka.admin import AdminClient
except ImportError:
    AdminClient = None  # type: ignore[assignment, misc]

try:
    from confluent_kafka.aio import AIOProducer
except ImportError:
    try:
        from confluent_kafka.experimental.aio import AIOProducer  # type: ignore[no-redef]
    except ImportError:
        AIOProducer = None  # type: ignore[assignment, misc]


# ---------------------------------------------------------------------------
# OutboxMessage — canonical data contract
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class OutboxMessage:
    """Canonical message published by the outbox relay.

    Every service MUST construct this before calling ``broker.publish()``.
    """

    event_id: str
    event_name: str
    partition_key: str
    payload: str  # Pre-serialised JSON string
    schema_version: int
    aggregate_type: str
    aggregate_id: str
    causation_id: str | None = None
    correlation_id: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract broker
# ---------------------------------------------------------------------------
class MessageBroker(abc.ABC):
    """Abstract message broker — technology-agnostic publish interface."""

    @abc.abstractmethod
    async def publish(self, message: OutboxMessage) -> None:
        """Publish an event. Raises on failure."""
        ...

    @abc.abstractmethod
    async def close(self) -> None:
        """Flush and close the broker connection."""
        ...

    @abc.abstractmethod
    async def check_health(self) -> None:
        """Raise when the broker is not healthy."""
        ...


# ---------------------------------------------------------------------------
# LogBroker — development / debug
# ---------------------------------------------------------------------------
class LogBroker(MessageBroker):
    """Logs events to stdout — for development and debugging."""

    async def publish(self, message: OutboxMessage) -> None:
        logger.info(
            "EVENT [%s] key=%s event=%s aggregate=%s/%s",
            message.event_name,
            message.partition_key,
            message.event_id,
            message.aggregate_type,
            message.aggregate_id,
        )

    async def close(self) -> None:
        pass

    async def check_health(self) -> None:
        pass


# ---------------------------------------------------------------------------
# NoOpBroker — testing
# ---------------------------------------------------------------------------
class NoOpBroker(MessageBroker):
    """Silent broker that discards all messages — for testing."""

    async def publish(self, message: OutboxMessage) -> None:
        pass

    async def close(self) -> None:
        pass

    async def check_health(self) -> None:
        pass


# ---------------------------------------------------------------------------
# KafkaBroker — production
# ---------------------------------------------------------------------------
class KafkaBroker(MessageBroker):
    """Production Kafka broker using Confluent AIOProducer.

    Guarantees:
    - ``acks=all`` + ``enable.idempotence=True`` by default
    - ``X-Correlation-ID`` and ``X-Causation-ID`` Kafka headers
    - Async produce with ``await delivery_future``
    """

    def __init__(
        self,
        producer_config: dict[str, Any],
        topic: str,
        *,
        correlation_id_getter: Any | None = None,
    ) -> None:
        if AIOProducer is None:
            raise RuntimeError("confluent-kafka with asyncio support is not installed.")

        # Enforce production defaults
        producer_config.setdefault("acks", "all")
        producer_config.setdefault("enable.idempotence", True)
        producer_config.setdefault("linger.ms", 10)  # Batching for throughput
        producer_config.setdefault("compression.type", "snappy")
        producer_config.setdefault("request.timeout.ms", 5000)

        self._topic = topic
        self._producer = AIOProducer(producer_config)
        self._admin = AdminClient(producer_config) if AdminClient else None
        self._correlation_id_getter = correlation_id_getter
        self._publish_timeout = 5.0  # Forensic fail-fast

    async def publish(self, message: OutboxMessage) -> None:
        """Publish with canonical header propagation."""
        headers: list[tuple[str, bytes]] = []

        # Correlation ID: from message, or from ContextVar
        c_id = message.correlation_id or ctx_correlation_id.get()
        if c_id:
            headers.append(("X-Correlation-ID", c_id.encode("utf-8")))

        # Causation ID: from message, or from ContextVar
        cau_id = message.causation_id or ctx_causation_id.get()
        if cau_id:
            headers.append(("X-Causation-ID", cau_id.encode("utf-8")))

        # Extra headers
        for key, value in message.headers.items():
            headers.append((key, value.encode("utf-8")))

        delivery_future = await self._producer.produce(
            self._topic,
            key=message.partition_key.encode("utf-8"),
            value=message.payload.encode("utf-8"),
            headers=headers,
        )
        # Elite Hardening: Fail fast to allow re-claiming by other workers
        await asyncio.wait_for(delivery_future, timeout=self._publish_timeout)

    async def close(self) -> None:
        """Flush buffered messages and close the producer."""
        await self._producer.flush()
        await self._producer.close()

    async def check_health(self) -> None:
        """Verify broker connectivity by requesting cluster metadata."""
        if self._admin is None:
            raise RuntimeError("AdminClient not available")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._list_topics)  # type: ignore[arg-type]

    def _list_topics(self) -> Any:
        return self._admin.list_topics(timeout=5)  # type: ignore[union-attr]
