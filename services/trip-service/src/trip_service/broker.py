"""Event broker for Trip Service — standardized to platform-common."""

from __future__ import annotations

from typing import Literal

from platform_common import KafkaBroker, LogBroker, MessageBroker, NoOpBroker

from trip_service.config import settings
from trip_service.observability import correlation_id


def _kafka_config() -> dict[str, object]:
    """Production-hardened Kafka configuration."""
    return {
        "bootstrap.servers": settings.kafka_bootstrap_servers,
        "client.id": settings.kafka_client_id,
        "acks": settings.kafka_acks,
        "enable.idempotence": settings.kafka_enable_idempotence,
        "security.protocol": settings.kafka_security_protocol,
        "linger.ms": settings.kafka_linger_ms,
        "batch.size": settings.kafka_batch_size,
        "compression.type": settings.kafka_compression_type,
    }


def create_broker(broker_type: Literal["kafka", "log", "noop"] | str | None = None) -> MessageBroker:
    """Factory function to create a standardized broker."""
    # Resolve backend
    resolved = broker_type or settings.resolved_broker_type

    if resolved == "kafka":
        return KafkaBroker(
            producer_config=_kafka_config(), topic=settings.kafka_topic, correlation_id_getter=correlation_id.get
        )
    if resolved == "log":
        return LogBroker()

    return NoOpBroker()
