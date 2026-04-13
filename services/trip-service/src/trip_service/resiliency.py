"""Resiliency patterns for the Trip Service."""

from __future__ import annotations

import logging
import time
from enum import Enum
from functools import wraps
from typing import Any, Callable

import httpx

from trip_service.observability import TRIP_CB_STATE_CHANGES_TOTAL, get_standard_labels
from trip_service.redis_client import get_redis

logger = logging.getLogger("trip_service.resiliency")


class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerError(Exception):
    """Raised when the circuit is open and refusing requests."""

    pass


class CircuitBreaker:
    """Redis-backed distributed circuit breaker for multi-pod service protection."""

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
        self.redis_key_prefix = f"cb:{name}"
        # Local fallback state in case Redis is down
        self._local_state = CircuitState.CLOSED
        self._local_count = 0
        self._local_last_time = 0.0

    @property
    def state(self) -> CircuitState:
        """Expose current local breaker state for probe callers."""
        return self._local_state

    async def _get_state_and_count(self) -> tuple[CircuitState, int, float]:
        """Fetch state, failure count, and last failure time from Redis, with local fallback."""
        try:
            redis = await get_redis()
            data = await redis.hgetall(self.redis_key_prefix)

            state_str = data.get("state", "CLOSED")
            count = int(data.get("count", 0))
            last_time = float(data.get("last_time", 0.0))

            return CircuitState(state_str), count, last_time
        except Exception as e:
            logger.error("Redis error in CircuitBreaker %s: %s. Using local fallback.", self.name, e)
            return self._local_state, self._local_count, self._local_last_time

    async def _set_state(self, state: CircuitState) -> None:
        """Update state in Redis and local fallback. Record metric."""
        self._local_state = state
        labels = get_standard_labels()
        labels.update({"breaker_name": self.name, "state": state.value})
        TRIP_CB_STATE_CHANGES_TOTAL.labels(**labels).inc()

        try:
            redis = await get_redis()
            await redis.hset(self.redis_key_prefix, "state", state.value)
        except Exception:
            pass

    async def _handle_failure(self) -> None:
        """Increment failure count in Redis and local fallback."""
        self._local_count += 1
        self._local_last_time = time.time()

        try:
            redis = await get_redis()
            count = await redis.hincrby(self.redis_key_prefix, "count", 1)
            last_time = time.time()
            await redis.hset(self.redis_key_prefix, "last_time", str(last_time))

            state_str = await redis.hget(self.redis_key_prefix, "state") or "CLOSED"
            state = CircuitState(state_str)

            if state != CircuitState.OPEN and count >= self.failure_threshold:
                await self._set_state(CircuitState.OPEN)
                logger.warning(
                    "Circuit %s transitioned to OPEN after %d consecutive failures",
                    self.name,
                    count,
                )
        except Exception:
            # Fallback logic if Redis fails during failure handling
            if self._local_state != CircuitState.OPEN and self._local_count >= self.failure_threshold:
                self._local_state = CircuitState.OPEN
                logger.warning(
                    "Circuit %s transitioned to OPEN (LOCAL FALLBACK) after %d failures", self.name, self._local_count
                )

    async def _reset(self) -> None:
        """Reset counts in Redis and local fallback."""
        self._local_count = 0
        self._local_last_time = 0.0
        self._local_state = CircuitState.CLOSED

        try:
            redis = await get_redis()
            await redis.hset(
                self.redis_key_prefix, mapping={"state": CircuitState.CLOSED.value, "count": "0", "last_time": "0.0"}
            )
        except Exception:
            pass

    def __call__(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """Decorator to wrap an async function with distributed circuit breaker logic."""

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            state, count, last_time = await self._get_state_and_count()

            if state == CircuitState.OPEN:
                if time.time() - last_time > self.recovery_timeout:
                    await self._set_state(CircuitState.HALF_OPEN)
                    state = CircuitState.HALF_OPEN
                    logger.info("Circuit %s transitioned to HALF_OPEN", self.name)
                else:
                    raise CircuitBreakerError(f"Circuit {self.name} is OPEN")

            try:
                result = await func(*args, **kwargs)
                if state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                    await self._reset()
                    logger.info("Circuit %s transitioned to CLOSED (Recovered)", self.name)
                return result
            except self.expected_exception as e:
                await self._handle_failure()
                raise e
            except Exception as e:
                raise e

        return wrapper


# Pre-defined breakers for core dependencies
fleet_breaker = CircuitBreaker("fleet-service")
location_breaker = CircuitBreaker("location-service")
