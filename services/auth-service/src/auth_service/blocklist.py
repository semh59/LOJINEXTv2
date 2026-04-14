"""JTI blocklist for explicit access token revocation."""

from __future__ import annotations

from auth_service.config import settings
from auth_service.redis_client import get_redis


async def block_token(jti: str, *, ttl_seconds: int | None = None) -> None:
    """Add a jti to the blocklist with the given TTL."""
    redis = await get_redis()
    ttl = ttl_seconds if ttl_seconds is not None else settings.access_token_blocklist_ttl_seconds
    await redis.setex(f"jti:blocked:{jti}", ttl, "1")


async def is_token_blocked(jti: str) -> bool:
    """Return True if the jti is on the blocklist."""
    redis = await get_redis()
    return bool(await redis.exists(f"jti:blocked:{jti}"))
