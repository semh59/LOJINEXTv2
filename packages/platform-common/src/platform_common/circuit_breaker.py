"""Distributed circuit breaker with Redis backend and local fallback.

Provides:
- ``CircuitBreaker`` — wraps async callables with fail-open/fail-closed
  semantics using a sliding-window failure counter in Redis.
- Falls back to local in-memory tracking when Redis is unavailable.
- Configurable failure threshold, recovery timeout, and half-open probes.

States:
  CLOSED  → Normal operation. Failures are counted.
  OPEN    → Requests are short-circuited. After ``recovery_timeout``,
            transitions to HALF_OPEN.
  HALF_OPEN → A limited number of probe requests are allowed through.
              If they succeed, transitions to CLOSED; if they fail,
              transitions back to OPEN.
"""

from __future__ import annotations

import asyncio
import enum
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

logger = logging.getLogger("platform_common.circuit_breaker")

T = TypeVar("T")


class CircuitState(str, enum.Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker tuning knobs."""

    name: str
    failure_threshold: int = 5
    recovery_timeout_seconds: float = 30.0
    half_open_max_calls: int = 2
    window_seconds: int = 60
    redis_key_prefix: str = "cb"


class CircuitOpenError(Exception):
    """Raised when the circuit is OPEN and the call is short-circuited."""

    def __init__(self, breaker_name: str, retry_after: float) -> None:
        self.breaker_name = breaker_name
        self.retry_after = retry_after
        super().__init__(
            f"Circuit breaker '{breaker_name}' is OPEN. Retry after {retry_after:.1f}s"
        )


class CircuitBreaker:
    """Distributed circuit breaker backed by Redis with local fallback.

    Usage::

        cb = CircuitBreaker(config=CircuitBreakerConfig(name="kafka-publish"))
        await cb.init(redis_client)  # optional — works without Redis too

        result = await cb.call(some_async_function, arg1, arg2)
    """

    def __init__(self, config: CircuitBreakerConfig) -> None:
        self._config = config
        self._redis: Any | None = None

        # Local fallback state
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def name(self) -> str:
        return self._config.name

    async def init(self, redis_client: Any | None = None) -> None:
        """Optionally attach a Redis client for distributed state."""
        self._redis = redis_client
        if redis_client:
            logger.info(
                "Circuit breaker '%s' using Redis-backed state",
                self._config.name,
            )
        else:
            logger.info(
                "Circuit breaker '%s' using local-only state",
                self._config.name,
            )

    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute ``func`` through the circuit breaker."""
        state = await self._get_state()

        if state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed < self._config.recovery_timeout_seconds:
                raise CircuitOpenError(
                    self._config.name,
                    self._config.recovery_timeout_seconds - elapsed,
                )
            # Recovery timeout elapsed → transition to HALF_OPEN
            await self._set_state(CircuitState.HALF_OPEN)
            self._half_open_calls = 0
            state = CircuitState.HALF_OPEN

        if state == CircuitState.HALF_OPEN:
            if self._half_open_calls >= self._config.half_open_max_calls:
                raise CircuitOpenError(self._config.name, 1.0)

        try:
            result = await func(*args, **kwargs)
        except Exception:
            await self._record_failure()
            raise

        await self._record_success(state)
        return result

    async def reset(self) -> None:
        """Manually reset to CLOSED."""
        async with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._half_open_calls = 0
            if self._redis:
                key = self._redis_key("failures")
                await self._redis.delete(key)
            logger.info("Circuit breaker '%s' manually reset", self._config.name)

    # ------------------------------------------------------------------
    # Internal state management
    # ------------------------------------------------------------------

    async def _get_state(self) -> CircuitState:
        if self._redis:
            try:
                raw = await self._redis.get(self._redis_key("state"))
                if raw:
                    return CircuitState(raw)
            except Exception:
                logger.warning(
                    "Circuit breaker '%s': Redis read failed, using local state",
                    self._config.name,
                )
        return self._state

    async def _set_state(self, state: CircuitState) -> None:
        async with self._lock:
            self._state = state
            if self._redis:
                try:
                    await self._redis.set(
                        self._redis_key("state"),
                        state.value,
                        ex=self._config.window_seconds * 2,
                    )
                except Exception:
                    logger.warning(
                        "Circuit breaker '%s': Redis write failed, local-only state",
                        self._config.name,
                    )

    async def _record_failure(self) -> None:
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in HALF_OPEN → back to OPEN
                await self._set_state(CircuitState.OPEN)
                logger.warning(
                    "Circuit breaker '%s': HALF_OPEN probe failed → OPEN",
                    self._config.name,
                )
                return

            # Distributed failure counting via Redis
            count = self._failure_count
            if self._redis:
                try:
                    key = self._redis_key("failures")
                    pipe = self._redis.pipeline()
                    await pipe.incr(key)
                    await pipe.expire(key, self._config.window_seconds)
                    results = await pipe.execute()
                    count = int(results[0])
                except Exception:
                    pass  # Fall back to local count

            if count >= self._config.failure_threshold:
                await self._set_state(CircuitState.OPEN)
                logger.warning(
                    "Circuit breaker '%s': threshold reached (%d/%d) → OPEN",
                    self._config.name,
                    count,
                    self._config.failure_threshold,
                )

    async def _record_success(self, previous_state: CircuitState) -> None:
        async with self._lock:
            if previous_state == CircuitState.HALF_OPEN:
                self._half_open_calls += 1
                if self._half_open_calls >= self._config.half_open_max_calls:
                    # All probes succeeded → close circuit
                    self._failure_count = 0
                    await self._set_state(CircuitState.CLOSED)
                    if self._redis:
                        try:
                            await self._redis.delete(self._redis_key("failures"))
                        except Exception:
                            pass
                    logger.info(
                        "Circuit breaker '%s': probes succeeded → CLOSED",
                        self._config.name,
                    )

    def _redis_key(self, suffix: str) -> str:
        return f"{self._config.redis_key_prefix}:{self._config.name}:{suffix}"
