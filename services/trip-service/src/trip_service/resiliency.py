"""Resiliency patterns for the Trip Service."""

import logging
import time
from enum import Enum
from functools import wraps
from typing import Callable, Type

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
        expected_exception: Type[Exception] = httpx.HTTPError,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0

    def __call__(self, func: Callable):
        """Decorator to wrap an async function with circuit breaker logic."""

        @wraps(func)
        async def wrapper(*args, **kwargs):
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    logger.info(f"Circuit {self.name} transitioned to HALF_OPEN")
                else:
                    raise CircuitBreakerError(f"Circuit {self.name} is OPEN")

            try:
                result = await func(*args, **kwargs)
                if self.state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                    self._reset()
                    logger.info(f"Circuit {self.name} transitioned to CLOSED (Recovered)")
                return result
            except self.expected_exception as e:
                # Trip on systematic HTTP failures (timeouts, 5xx, etc.)
                # Note: httpx exceptions are already classified in the wrapped functions
                self._handle_failure()
                raise e
            except Exception as e:
                # Pass through non-HTTP exceptions (validation, logic bugs)
                raise e

        return wrapper

    def _handle_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.state != CircuitState.OPEN and self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit {self.name} transitioned to OPEN after {self.failure_count} consecutive failures")

    def _reset(self):
        self.state = CircuitState.CLOSED
        self.failure_count = 0


# Pre-defined breakers for core dependencies
fleet_breaker = CircuitBreaker("fleet-service")
location_breaker = CircuitBreaker("location-service")
