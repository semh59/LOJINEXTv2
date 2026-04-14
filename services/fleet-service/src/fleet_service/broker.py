"""Event broker for Fleet Service — standardized to platform-common."""

from __future__ import annotations

from typing import Literal

from platform_common import KafkaBroker, LogBroker, MessageBroker, NoOpBroker

from fleet_service.config import settings
from fleet_service.observability import correlation_id


def _kafka_config() -> dict[str, object]:
    """Production-hardened Kafka configuration."""
    config: dict[str, object] = {
        "bootstrap.servers": settings.kafka_bootstrap_servers,
        "client.id": settings.kafka_client_id,
        "security.protocol": settings.kafka_security_protocol,
        "acks": settings.kafka_acks,
        "enable.idempotence": settings.kafka_enable_idempotence,
        "linger.ms": settings.kafka_linger_ms,
        "batch.size": settings.kafka_batch_size,
        "compression.type": settings.kafka_compression_type,
    }
    if settings.kafka_sasl_mechanism:
        config["sasl.mechanism"] = settings.kafka_sasl_mechanism
    if settings.kafka_sasl_username:
        config["sasl.username"] = settings.kafka_sasl_username
    if settings.kafka_sasl_password:
        config["sasl.password"] = settings.kafka_sasl_password
    return config


def create_broker(broker_type: Literal["kafka", "log", "noop"] | str | None = None) -> MessageBroker:
    """Factory function to create a standardized broker."""
    b_type = broker_type or settings.resolved_broker_type

    if b_type == "kafka":
        return KafkaBroker(
            producer_config=_kafka_config(), topic=settings.kafka_topic, correlation_id_getter=correlation_id.get
        )
    if b_type == "log":
        return LogBroker()

    return NoOpBroker()
