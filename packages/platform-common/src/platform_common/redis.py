"""Canonical Redis connection manager for all LOJINEXT services.

Provides:
- Singleton Redis client with configurable connection pool
- Health probe (``check_health``)
- Test override via ``override_redis``
- Graceful shutdown via ``close_redis``
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import redis.asyncio as aioredis

logger = logging.getLogger("platform_common.redis")

_redis: aioredis.Redis | None = None


@dataclass(frozen=True, slots=True)
class RedisConfig:
    """Redis connection configuration."""

    url: str = "redis://localhost:6379/0"
    max_connections: int = 20
    socket_timeout: float = 2.0
    socket_connect_timeout: float = 2.0
    retry_on_timeout: bool = True
    decode_responses: bool = True
    health_check_interval: int = 30


async def init_redis(config: RedisConfig) -> aioredis.Redis:
    """Initialise the Redis singleton with a connection pool.

    Safe to call multiple times — returns the existing client if
    already initialised.
    """
    global _redis
    if _redis is not None:
        return _redis

    pool = aioredis.ConnectionPool.from_url(
        config.url,
        max_connections=config.max_connections,
        socket_timeout=config.socket_timeout,
        socket_connect_timeout=config.socket_connect_timeout,
        retry_on_timeout=config.retry_on_timeout,
        decode_responses=config.decode_responses,
        health_check_interval=config.health_check_interval,
    )
    _redis = aioredis.Redis(connection_pool=pool)
    logger.info(
        "Redis initialised — url=%s max_connections=%d",
        _mask_url(config.url),
        config.max_connections,
    )
    return _redis


async def get_redis() -> aioredis.Redis:
    """Return the shared Redis client.

    Raises ``RuntimeError`` if ``init_redis`` has not been called.
    """
    if _redis is None:
        raise RuntimeError("Redis not initialised. Call init_redis() during app startup.")
    return _redis


async def close_redis() -> None:
    """Close the Redis connection pool on application shutdown."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
        logger.info("Redis connection closed")


async def check_redis_health() -> None:
    """Ping Redis and raise on failure."""
    if _redis is None:
        raise RuntimeError("Redis not initialised")
    await _redis.ping()


def override_redis(client: aioredis.Redis) -> None:
    """Replace the Redis client — used in tests to inject fakeredis."""
    global _redis
    _redis = client


def _mask_url(url: str) -> str:
    """Mask password in Redis URL for safe logging."""
    if "@" in url:
        prefix, rest = url.rsplit("@", 1)
        scheme_end = prefix.find("://") + 3
        return prefix[:scheme_end] + "***@" + rest
    return url
