"""Redis connection management for Identity Service."""

from __future__ import annotations

import redis.asyncio as aioredis

from identity_service.config import settings

_redis: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Return the shared Redis client, initialising it on first call."""
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def close_redis() -> None:
    """Close the Redis connection on application shutdown."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


def override_redis(client: aioredis.Redis) -> None:
    """Replace the Redis client — used in tests to inject fakeredis."""
    global _redis
    _redis = client
