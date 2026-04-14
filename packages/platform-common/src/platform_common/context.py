from contextvars import ContextVar
from typing import Optional, cast

# Correlation and Causation ContextVars for cross-service tracing propagation.
# Used by RequestIdMiddleware, Kafka consumers, and common logging formatters.
correlation_id: ContextVar[Optional[str]] = ContextVar("correlation_id", default=cast(Optional[str], None))
causation_id: ContextVar[Optional[str]] = ContextVar("causation_id", default=cast(Optional[str], None))
