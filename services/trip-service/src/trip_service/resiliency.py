"""Resiliency patterns for the Trip Service."""

import logging
import time
from enum import Enum
from functools import wraps
from typing import Any, Callable

import httpx

logger = logging.getLogger("trip_service.resiliency")


class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerError(Exception):
    """Raised when the circuit is open and refusing requests."""

    pass


class CircuitBreaker:
    """A simple in-memory circuit breaker for external service protection."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        expected_exception: type[Exception] = httpx.HTTPError,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0

    def __call__(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """Decorator to wrap an async function with circuit breaker logic."""

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    logger.info("Circuit %s transitioned to HALF_OPEN", self.name)
                else:
                    raise CircuitBreakerError(f"Circuit {self.name} is OPEN")

            try:
                result = await func(*args, **kwargs)
                if self.state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                    self._reset()
                    logger.info("Circuit %s transitioned to CLOSED (Recovered)", self.name)
                return result
            except self.expected_exception as e:
                # Trip on systematic HTTP failures (timeouts, 5xx, etc.)
                self._handle_failure()
                raise e
            except Exception as e:
                # Pass through non-HTTP exceptions (validation, logic bugs)
                raise e

        return wrapper

    def _handle_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.state != CircuitState.OPEN and self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(
                "Circuit %s transitioned to OPEN after %d consecutive failures",
                self.name,
                self.failure_count,
            )

    def _reset(self) -> None:
        self.state = CircuitState.CLOSED
        self.failure_count = 0


# Pre-defined breakers for core dependencies
fleet_breaker = CircuitBreaker("fleet-service")
location_breaker = CircuitBreaker("location-service")
