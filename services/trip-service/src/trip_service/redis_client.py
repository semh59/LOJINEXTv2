"""Redis connection management for Trip Service."""

from __future__ import annotations

import redis.asyncio as aioredis
from trip_service.config import settings

_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Return the shared Redis client, initialising it on first call."""
    global _redis
    if _redis is None:
        pool = aioredis.ConnectionPool.from_url(
            settings.redis_url,
            max_connections=settings.redis_max_connections,
            socket_timeout=settings.redis_socket_timeout,
            retry_on_timeout=settings.redis_retry_on_timeout,
            decode_responses=True,
        )
        _redis = aioredis.Redis(connection_pool=pool)
    return _redis


async def close_redis() -> None:
    """Close the Redis connection on application shutdown."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


def override_redis(client: aioredis.Redis) -> None:
    """Replace the Redis client — used in tests."""
    global _redis
    _redis = client
