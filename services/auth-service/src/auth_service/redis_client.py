"""Pooled Redis client for Auth Service ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â standardized to platform-common."""

from __future__ import annotations

from auth_service.config import settings
from platform_common import (
    RedisConfig,
    init_redis,
    get_redis as _platform_get_redis,
    close_redis as _platform_close_redis,
)


async def setup_redis() -> None:
    """Initialise the pooled Redis connection."""
    config = RedisConfig(
        url=settings.redis_url,
    )
    await init_redis(config)


async def get_redis():
    """Compatibility wrapper for auth-service to get Redis client."""
    return await _platform_get_redis()


async def close_redis() -> None:
    """Compatibility wrapper for auth-service to close Redis."""
    await _platform_close_redis()


def override_redis(client) -> None:
    """Compatibility wrapper for tests to override Redis."""
    from platform_common import override_redis as _platform_override_redis

    _platform_override_redis(client)
