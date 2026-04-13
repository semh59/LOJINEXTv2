"""HTTP client for driver-service internal endpoints."""

from __future__ import annotations

from telegram_service.auth import _cache_get, _cache_set
from telegram_service.config import settings
from telegram_service.http_clients import get_headers, http_manager
from telegram_service.schemas import DriverLookupResult


async def lookup_by_telegram_id(telegram_user_id: int) -> DriverLookupResult | None:
    """Resolve a Telegram user ID to a driver record.

    Returns None if no driver is registered with that Telegram user ID.
    Uses an in-memory cache to reduce driver-service load.
    """
    cached = _cache_get(telegram_user_id)
    if cached is not None:
        driver_id, full_name = cached
        return DriverLookupResult(
            driver_id=driver_id,
            full_name=full_name,
            telegram_user_id=str(telegram_user_id),
            status="ACTIVE",
            is_assignable=True,
        )

    resp = await http_manager.request(
        "GET",
        f"{settings.driver_service_url}/internal/v1/drivers/lookup",
        params={"telegram_user_id": str(telegram_user_id)},
        headers=await get_headers(),
    )

    if resp.status_code == 404:
        return None

    resp.raise_for_status()
    data = resp.json()
    result = DriverLookupResult.model_validate(data)
    _cache_set(telegram_user_id, result.driver_id, result.full_name)
    return result
