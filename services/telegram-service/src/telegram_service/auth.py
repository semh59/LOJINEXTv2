"""Outbound service authentication and driver identity resolution."""

from __future__ import annotations

import time

from platform_auth import ServiceTokenAcquisitionError, ServiceTokenCache

from telegram_service.config import settings

_SERVICE_TOKEN_CACHE = ServiceTokenCache()

# Simple in-memory driver lookup cache: telegram_user_id -> (driver_id, full_name, expiry)
_driver_cache: dict[int, tuple[str, str, float]] = {}


async def issue_service_token() -> str:
    """Return an outbound service JWT for calling other platform services."""
    try:
        return await _SERVICE_TOKEN_CACHE.get_token(
            service_name=settings.service_name,
            audience=settings.auth_audience or None,
            token_url=settings.auth_service_token_url,
            client_id=settings.auth_service_client_id,
            client_secret=settings.auth_service_client_secret,
        )
    except ServiceTokenAcquisitionError as exc:
        raise RuntimeError(f"Service token acquisition failed: {exc}") from exc


def _cache_get(telegram_user_id: int) -> tuple[str, str] | None:
    """Return (driver_id, full_name) from cache if not expired, else None."""
    entry = _driver_cache.get(telegram_user_id)
    if entry is None:
        return None
    driver_id, full_name, expiry = entry
    if time.monotonic() > expiry:
        del _driver_cache[telegram_user_id]
        return None
    return driver_id, full_name


def _cache_set(telegram_user_id: int, driver_id: str, full_name: str) -> None:
    """Store driver identity in cache for TTL seconds."""
    expiry = time.monotonic() + settings.driver_cache_ttl_seconds
    _driver_cache[telegram_user_id] = (driver_id, full_name, expiry)


def cache_clear() -> None:
    """Clear the driver identity cache (used in tests)."""
    _driver_cache.clear()
