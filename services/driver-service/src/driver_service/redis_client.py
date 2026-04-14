"""Pooled Redis client for Driver Service — standardized to platform-common."""

from __future__ import annotations

from platform_common import (
    RedisConfig,
    close_redis,
    init_redis,
)

__all__ = ["setup_redis", "close_redis"]

from driver_service.config import settings


async def setup_redis() -> None:
    """Initialise the pooled Redis connection."""
    config = RedisConfig(
        url=settings.redis_url,
        max_connections=settings.redis_max_connections,
        socket_timeout=settings.redis_socket_timeout,
        retry_on_timeout=settings.redis_retry_on_timeout,
    )
    await init_redis(config)
