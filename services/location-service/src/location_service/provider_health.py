"""Cached live-provider probes used by readiness checks."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from location_service.config import settings
from location_service.providers.mapbox_directions import MapboxDirectionsClient
from location_service.providers.ors_validation import ORSValidationClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderProbeResult:
    """Cached live-provider probe outcome."""

    mapbox_live: str
    ors_live: str
    checked_at_utc: datetime


_probe_lock = asyncio.Lock()
_cached_probe: ProviderProbeResult | None = None


def _now_utc() -> datetime:
    return datetime.now(UTC)


async def _probe_mapbox() -> str:
    if not settings.mapbox_api_key:
        return "missing"

    client = MapboxDirectionsClient()
    try:
        await client.get_route(
            origin_lng=settings.provider_probe_origin_lng,
            origin_lat=settings.provider_probe_origin_lat,
            dest_lng=settings.provider_probe_dest_lng,
            dest_lat=settings.provider_probe_dest_lat,
        )
        return "ok"
    except Exception as exc:  # pragma: no cover - exercised via router tests
        logger.warning("Mapbox live probe failed: %s", exc)
        return "unavailable"


async def _probe_ors() -> str:
    if not settings.enable_ors_validation:
        return "disabled"
    if not settings.ors_api_key or not settings.ors_base_url:
        return "missing"

    client = ORSValidationClient()
    try:
        result = await client.get_validation(
            origin_lng=settings.provider_probe_origin_lng,
            origin_lat=settings.provider_probe_origin_lat,
            dest_lng=settings.provider_probe_dest_lng,
            dest_lat=settings.provider_probe_dest_lat,
        )
    except Exception as exc:  # pragma: no cover - exercised via router tests
        logger.warning("ORS live probe failed: %s", exc)
        return "unavailable"

    return "ok" if result.status == "VALIDATED" else "unavailable"


async def get_provider_probe_result() -> ProviderProbeResult:
    """Return a cached live-provider probe, refreshing it when the TTL expires."""
    global _cached_probe

    now = _now_utc()
    ttl = timedelta(seconds=settings.provider_probe_ttl_seconds)
    if _cached_probe is not None and now - _cached_probe.checked_at_utc <= ttl:
        return _cached_probe

    async with _probe_lock:
        now = _now_utc()
        if _cached_probe is not None and now - _cached_probe.checked_at_utc <= ttl:
            return _cached_probe

        mapbox_live, ors_live = await asyncio.gather(_probe_mapbox(), _probe_ors())
        _cached_probe = ProviderProbeResult(
            mapbox_live=mapbox_live,
            ors_live=ors_live,
            checked_at_utc=now,
        )
        return _cached_probe


def provider_probe_age_seconds(result: ProviderProbeResult) -> int:
    """Return the age of a cached probe result in whole seconds."""
    return max(0, int((_now_utc() - result.checked_at_utc).total_seconds()))


async def reset_provider_probe_cache() -> None:
    """Clear the cached probe result for tests or process resets."""
    global _cached_probe
    async with _probe_lock:
        _cached_probe = None
