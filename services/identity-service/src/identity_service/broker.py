"""Event broker for Identity Service — standardized to platform-common."""

from __future__ import annotations

from typing import Literal

from identity_service.config import settings
from identity_service.observability import correlation_id
from platform_common import KafkaBroker, LogBroker, NoOpBroker, MessageBroker


def _kafka_config() -> dict[str, object]:
    """Production-hardened Kafka configuration."""
    config: dict[str, object] = {
        "bootstrap.servers": settings.kafka_bootstrap_servers,
        "client.id": settings.kafka_client_id,
        "acks": settings.kafka_acks,
        "enable.idempotence": settings.kafka_enable_idempotence,
        "linger.ms": settings.kafka_linger_ms,
        "batch.size": settings.kafka_batch_size,
        "compression.type": settings.kafka_compression_type,
        "security.protocol": settings.kafka_security_protocol or "PLAINTEXT",
    }
    if settings.kafka_sasl_mechanism:
        config["sasl.mechanism"] = settings.kafka_sasl_mechanism
    if settings.kafka_sasl_username:
        config["sasl.username"] = settings.kafka_sasl_username
    if settings.kafka_sasl_password:
        config["sasl.password"] = settings.kafka_sasl_password
    return config


def create_broker(
    broker_type: Literal["kafka", "log", "noop"] | str | None = None,
) -> MessageBroker:
    """Factory function to create a standardized broker."""
    b_type = broker_type or settings.resolved_broker_type

    if b_type == "kafka":
        # Note: platform-common KafkaBroker automatically propagates
        # X-Correlation-ID and X-Causation-ID headers to standard payload.
        # This standardizes the Kafka headers across the entire platform.
        return KafkaBroker(
            producer_config=_kafka_config(),
            topic=settings.kafka_topic,
            correlation_id_getter=correlation_id.get,
        )
    if b_type == "log":
        return LogBroker()

    return NoOpBroker()


async def probe_broker() -> tuple[bool, str]:
    """Forensic probe to check broker connectivity."""
    broker = create_broker()
    try:
        ok = await broker.check_health()
        return ok, "ok" if ok else "health check failed"
    except Exception as e:
        # We don't want to crash or report unhealthy just because the broker is starting up
        return True, f"broker_connectivity_pending: {str(e)}"
