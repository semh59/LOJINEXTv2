"""Redis client management for Trip Service — standardized to platform-common."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from platform_common import (
    RedisConfig,
)
from platform_common import (
    close_redis as _platform_close_redis,
)
from platform_common import (
    get_redis as _platform_get_redis,
)
from platform_common import (
    init_redis as _platform_init_redis,
)

from trip_service.config import settings

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger("trip_service.redis")


async def setup_redis() -> None:
    """Initialise the global standardized Redis connection pool."""
    config = RedisConfig(
        url=settings.redis_url,
        max_connections=settings.redis_max_connections,
        socket_timeout=settings.redis_socket_timeout,
        retry_on_timeout=settings.redis_retry_on_timeout,
    )
    await _platform_init_redis(config)


async def get_redis() -> Redis:
    """Return the global standardized Redis client."""
    return await _platform_get_redis()


async def close_redis() -> None:
    """Gracefully close the global standardized Redis pool."""
    await _platform_close_redis()
