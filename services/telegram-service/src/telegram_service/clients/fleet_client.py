"""HTTP client for fleet-service internal endpoints."""

from __future__ import annotations

import logging


from telegram_service.config import settings
from telegram_service.http_clients import get_headers, http_manager

logger = logging.getLogger(__name__)


async def lookup_vehicle_by_plate(normalized_plate: str) -> str | None:
    """Lookup a vehicle's ULID by its normalized plate via fleet-service."""
    client = http_manager.get_client()
    try:
        resp = await client.get(
            f"{settings.fleet_service_url}/internal/v1/vehicles/by-plate/{normalized_plate}",
            headers=await get_headers(),
        )
        if resp.status_code == 200:
            return resp.json().get("vehicle_id")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
    except Exception:
        logger.exception("Failed to lookup vehicle by plate: %s", normalized_plate)
        return None
    return None


async def lookup_trailer_by_plate(normalized_plate: str) -> str | None:
    """Lookup a trailer's ULID by its normalized plate via fleet-service."""
    client = http_manager.get_client()
    try:
        resp = await client.get(
            f"{settings.fleet_service_url}/internal/v1/trailers/by-plate/{normalized_plate}",
            headers=await get_headers(),
        )
        if resp.status_code == 200:
            return resp.json().get("trailer_id")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
    except Exception:
        logger.exception("Failed to lookup trailer by plate: %s", normalized_plate)
        return None
    return None
