"""HTTP client for Trip Service (outbound S2S calls).

Used by hard-delete pipeline to check if an asset is referenced by active trips.
Implements: httpx + signed JWT + simple circuit breaker.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from fleet_service.auth import sign_service_token
from fleet_service.config import settings
from fleet_service.errors import DependencyUnavailableError

logger = logging.getLogger("fleet_service.clients.trip_client")

# --- Circuit Breaker State (module-level) ---

_failure_count: int = 0
_last_failure_time: float = 0.0
_state: str = "CLOSED"  # CLOSED | OPEN | HALF_OPEN


def _check_breaker() -> None:
    """Raise immediately if circuit is OPEN and cooldown hasn't elapsed."""
    global _state  # noqa: PLW0603
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


def _record_success() -> None:
    global _failure_count, _state  # noqa: PLW0603
    if _state == "HALF_OPEN":
        _failure_count = 0
        _state = "CLOSED"
        logger.info("trip-client circuit breaker → CLOSED")
    elif _state == "CLOSED":
        _failure_count = 0


def _record_failure() -> None:
    global _failure_count, _last_failure_time, _state  # noqa: PLW0603
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

    Returns dict with at least: {"has_references": bool, ...}
    Raises DependencyUnavailableError on failure / circuit-open.
    """
    _check_breaker()

    url = f"{settings.trip_service_base_url}/internal/v1/references/check"
    token = sign_service_token(settings.trip_service_jwt_secret, "fleet-to-trip")
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
            resp = await client.post(url, json=payload, headers={"Authorization": f"Bearer {token}"})
            resp.raise_for_status()
            _record_success()
            return resp.json()
    except Exception as exc:
        _record_failure()
        logger.error("trip-client check_asset_references(%s, %s) failed: %s", asset_id, asset_type, exc)
        raise DependencyUnavailableError("trip-service") from exc
