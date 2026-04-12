"""Pooled Redis client for Driver Service — standardized to platform-common."""

from __future__ import annotations

from driver_service.config import settings
from platform_common import (
    RedisConfig,
    init_redis,
    get_redis,
    close_redis,
    check_redis_health,
    override_redis,
)


async def setup_redis() -> None:
    """Initialise the pooled Redis connection."""
    config = RedisConfig(
        url=settings.redis_url,
        max_connections=settings.redis_max_connections,
        socket_timeout=settings.redis_socket_timeout,
        retry_on_timeout=settings.redis_retry_on_timeout,
    )
    await init_redis(config)
