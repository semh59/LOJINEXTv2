"""Event broker for Location Service — standardized to platform-common."""

from __future__ import annotations

from typing import Literal

from location_service.config import settings
from location_service.observability import correlation_id
from platform_common import KafkaBroker, LogBroker, NoOpBroker, MessageBroker


def _kafka_config() -> dict[str, object]:
    """Production-hardened Kafka configuration."""
    return {
        "bootstrap.servers": settings.kafka_bootstrap_servers,
        "client.id": settings.kafka_client_id,
        "acks": settings.kafka_acks,
        "enable.idempotence": settings.kafka_enable_idempotence,
        "security.protocol": settings.kafka_security_protocol,
    }


def create_broker(broker_type: Literal["kafka", "log", "noop"] | str | None = None) -> MessageBroker:
    """Factory function to create a standardized broker."""
    # Resolve backend
    if broker_type:
        resolved = broker_type
    elif settings.kafka_bootstrap_servers and settings.environment != "dev":
        resolved = "kafka"
    elif settings.environment == "dev":
        resolved = "log"
    else:
        resolved = "noop"

    if resolved == "kafka":
        return KafkaBroker(
            producer_config=_kafka_config(), topic=settings.kafka_topic, correlation_id_getter=correlation_id.get
        )
    if resolved == "log":
        return LogBroker()

    return NoOpBroker()
