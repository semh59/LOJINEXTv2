"""Resiliency patterns for the Trip Service — aligned with platform-common."""

from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Callable, cast

from platform_common.circuit_breaker import (
    CircuitBreaker as StandardCB,
)
from platform_common.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitOpenError,
    CircuitState,
)

from trip_service.redis_client import get_redis

logger = logging.getLogger("trip_service.resiliency")

# Alias for backward compatibility with existing exception handlers
CircuitBreakerError = CircuitOpenError


class CircuitBreaker:
    """Wrapper around platform-common's CircuitBreaker to provide the legacy decorator API.

    Ensures that the Distributed Circuit Breaker (HATA-1) is used consistently.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        expected_exception: type[Exception] = Exception,
    ) -> None:
        self._engine = StandardCB(
            config=CircuitBreakerConfig(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout_seconds=recovery_timeout,
            )
        )
        self.expected_exception = expected_exception

    @property
    def state(self) -> CircuitState:
        return self._engine.state

    @property
    def name(self) -> str:
        return self._engine.name

    def __call__(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """Decorator to wrap an async function with standard circuit breaker logic."""

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Lazy initialize Redis client to ensure it's available in the current event loop
            if self._engine._redis is None:
                try:
                    redis = await get_redis()
                    await self._engine.init(redis)
                except Exception as e:
                    logger.debug("Failed to initialize Redis for breaker %s: %s", self.name, e)

            try:
                # The standard engine records failures for any Exception in its .call() method.
                # To maintain legacy 'expected_exception' behavior, we filter if needed,
                # but generally, standardizing on 'all exceptions' is more resilient.
                return await self._engine.call(func, *args, **kwargs)
            except CircuitOpenError:
                raise
            except Exception as e:
                # If we have a specific exception filter, we can re-evaluate.
                # For now, we propagate everything just like the engine does.
                raise e

        return cast(Callable[..., Any], wrapper)


# Pre-defined breakers for core dependencies
fleet_breaker = CircuitBreaker("fleet-service")
location_breaker = CircuitBreaker("location-service")
