"""HTTP client for Trip Service (outbound S2S calls).

Used by hard-delete pipeline to check if an asset is referenced by active trips.
Implements: httpx + signed JWT + simple circuit breaker.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from fleet_service.auth import issue_service_token
from fleet_service.config import settings
from fleet_service.errors import DependencyUnavailableError
from fleet_service.observability import correlation_id

logger = logging.getLogger("fleet_service.clients.trip_client")

# --- Circuit Breaker State (module-level) ---

_failure_count: int = 0
_last_failure_time: float = 0.0
_state: str = "CLOSED"  # CLOSED | OPEN | HALF_OPEN
_lock = asyncio.Lock()


async def _check_breaker() -> None:
    """Raise immediately if circuit is OPEN and cooldown hasn't elapsed."""
    global _state  # noqa: PLW0603
    async with _lock:
        if _state == "CLOSED":
            return
        if _state == "OPEN":
            elapsed = time.monotonic() - _last_failure_time
            if elapsed >= settings.breaker_half_open_after_seconds:
                _state = "HALF_OPEN"
                logger.info("trip-client circuit breaker → HALF_OPEN")
                return
            raise DependencyUnavailableError("trip-service")
        # HALF_OPEN → allow the request through


async def _record_success() -> None:
    global _failure_count, _state  # noqa: PLW0603
    async with _lock:
        if _state == "HALF_OPEN":
            _failure_count = 0
            _state = "CLOSED"
            logger.info("trip-client circuit breaker → CLOSED")
        elif _state == "CLOSED":
            _failure_count = 0


async def _record_failure() -> None:
    global _failure_count, _last_failure_time, _state  # noqa: PLW0603
    async with _lock:
        _failure_count += 1
        _last_failure_time = time.monotonic()
        if _state == "HALF_OPEN":
            _state = "OPEN"
            logger.warning("trip-client circuit breaker → OPEN (half-open probe failed)")
        elif _failure_count >= settings.breaker_open_threshold:
            _state = "OPEN"
            logger.warning("trip-client circuit breaker → OPEN (threshold=%d reached)", settings.breaker_open_threshold)


# --- Public API ---


async def check_asset_references(asset_id: str, asset_type: str) -> dict[str, Any]:
    """Call trip-service to check if an asset is referenced by active trips.

    Returns a normalized reference-check payload.
    Raises DependencyUnavailableError on failure / circuit-open.
    """
    await _check_breaker()

    url = f"{settings.trip_service_base_url}/internal/v1/assets/reference-check"
    token = await issue_service_token()
    payload = {"asset_id": asset_id, "asset_type": asset_type}

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=settings.http_connect_timeout,
                read=settings.http_read_timeout,
                write=settings.http_read_timeout,
                pool=settings.http_total_timeout,
            ),
        ) as client:
            headers = {"Authorization": f"Bearer {token}"}
            if c_id := correlation_id.get():
                headers["X-Correlation-ID"] = c_id

            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            await _record_success()
            return {
                "asset_id": asset_id,
                "asset_type": asset_type,
                "is_referenced": bool(data.get("is_referenced", False)),
                "has_references": bool(data.get("is_referenced", False)),
                "active_trip_count": int(data.get("active_trip_count", 0) or 0),
            }
    except Exception as exc:
        await _record_failure()
        logger.error("trip-client check_asset_references(%s, %s) failed: %s", asset_id, asset_type, exc)
        raise DependencyUnavailableError("trip-service") from exc
