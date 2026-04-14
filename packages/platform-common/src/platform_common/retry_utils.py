"""Resiliency utilities for LOJINEXT services.

Provides:
- ``retry`` decorator with exponential backoff and jitter.
- ``AsyncTimeout`` context manager.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
from typing import Any, Callable, TypeVar, ParamSpec

logger = logging.getLogger("platform_common.resiliency")

T = TypeVar("T")
P = ParamSpec("P")


def retry(
    *,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
) -> Callable[[Callable[P, Any]], Callable[P, Any]]:
    """Decorator to retry an async function with exponential backoff.

    Args:
        exceptions: Tuple of exceptions to catch and retry on.
        max_attempts: Maximum number of attempts (including the first one).
        initial_delay: Delay before the first retry in seconds.
        max_delay: Maximum delay between retries in seconds.
        backoff_factor: Factor by which the delay increases each attempt.
        jitter: If True, adds random jitter to the delay.
    """

    def decorator(func: Callable[P, Any]) -> Callable[P, Any]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            attempt = 1
            delay = initial_delay

            while True:
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    if attempt >= max_attempts:
                        logger.error(
                            "Function %s failed after %d attempts: %s",
                            func.__name__,
                            attempt,
                            exc,
                        )
                        raise

                    actual_delay = delay
                    if jitter:
                        actual_delay *= random.uniform(0.8, 1.2)

                    logger.warning(
                        "Function %s failed (attempt %d/%d), retrying in %.2fs: %s",
                        func.__name__,
                        attempt,
                        max_attempts,
                        actual_delay,
                        exc,
                    )

                    await asyncio.sleep(actual_delay)
                    attempt += 1
                    delay = min(delay * backoff_factor, max_delay)

        return wrapper

    return decorator


class AsyncTimeout:
    """Context manager for async timeouts."""

    def __init__(self, seconds: float):
        self.seconds = seconds
        self._task = None

    async def __aenter__(self):
        return await asyncio.wait_for(asyncio.sleep(0), timeout=self.seconds)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
