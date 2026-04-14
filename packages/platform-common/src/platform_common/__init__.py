"""Canonical platform-common exports for all LOJINEXT services."""

from .utils import utc_now
from .context import correlation_id, causation_id
from .middleware import RequestIdMiddleware, PrometheusMiddleware
from .outbox import OutboxPublishStatus
from .broker import (
    MessageBroker,
    OutboxMessage,
    KafkaBroker,
    LogBroker,
    NoOpBroker,
    RobustJSONEncoder,
)
from .redis_utils import (
    RedisConfig,
    init_redis,
    get_redis,
    close_redis,
    check_redis_health,
    override_redis,
)
from .tracing import setup_tracing, instrument_app, get_tracer, shutdown_tracing
from .circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    CircuitOpenError,
)
from .retry_utils import retry, AsyncTimeout
from .outbox_relay import OutboxRelayBase
from .logging_utils import setup_logging
from .consumer import KafkaConsumerBase

__all__ = [
    "OutboxPublishStatus",
    "MessageBroker",
    "OutboxMessage",
    "KafkaBroker",
    "LogBroker",
    "NoOpBroker",
    "RobustJSONEncoder",
    "RedisConfig",
    "init_redis",
    "get_redis",
    "close_redis",
    "check_redis_health",
    "override_redis",
    "setup_tracing",
    "instrument_app",
    "get_tracer",
    "shutdown_tracing",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitState",
    "CircuitOpenError",
    "retry",
    "AsyncTimeout",
    "OutboxRelayBase",
    "setup_logging",
    "KafkaConsumerBase",
    "utc_now",
    "correlation_id",
    "causation_id",
    "RequestIdMiddleware",
    "PrometheusMiddleware",
]
