"""HTTP client for Driver Service (outbound S2S calls).

Used by trip-compat validation to verify driver existence and status.
Implements: httpx + signed JWT + simple circuit breaker.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from fleet_service.auth import issue_service_token
from fleet_service.config import settings
from fleet_service.errors import DependencyUnavailableError
from fleet_service.observability import correlation_id

logger = logging.getLogger("fleet_service.clients.driver_client")

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
            logger.info("driver-client circuit breaker → HALF_OPEN")
            return
        raise DependencyUnavailableError("driver-service")
    # HALF_OPEN → allow the request through


def _record_success() -> None:
    global _failure_count, _state  # noqa: PLW0603
    if _state == "HALF_OPEN":
        _failure_count = 0
        _state = "CLOSED"
        logger.info("driver-client circuit breaker → CLOSED")
    elif _state == "CLOSED":
        _failure_count = 0


def _record_failure() -> None:
    global _failure_count, _last_failure_time, _state  # noqa: PLW0603
    _failure_count += 1
    _last_failure_time = time.monotonic()
    if _state == "HALF_OPEN":
        _state = "OPEN"
        logger.warning("driver-client circuit breaker → OPEN (half-open probe failed)")
    elif _failure_count >= settings.breaker_open_threshold:
        _state = "OPEN"
        logger.warning("driver-client circuit breaker → OPEN (threshold=%d reached)", settings.breaker_open_threshold)


# --- Public API ---


async def validate_driver(driver_id: str) -> dict[str, Any]:
    """Call driver-service eligibility check for a single driver ID.

    Returns a normalized single-driver result payload.
    Raises DependencyUnavailableError on failure or circuit-open.
    """
    _check_breaker()

    url = f"{settings.driver_service_base_url}/internal/v1/drivers/eligibility/check"
    token = await issue_service_token()
    payload = {"driver_ids": [driver_id]}

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
            items = data.get("items", [])
            if not isinstance(items, list) or not items:
                raise ValueError("Driver eligibility response did not include items.")
            item = items[0]
            if not isinstance(item, dict):
                raise ValueError("Driver eligibility response item was not an object.")
            _record_success()
            return {
                "driver_id": driver_id,
                "exists": bool(item.get("exists", False)),
                "status": item.get("status"),
                "lifecycle_state": item.get("lifecycle_state"),
                "is_assignable": bool(item.get("is_assignable", False)),
            }
    except Exception as exc:
        _record_failure()
        logger.error("driver-client validate_driver(%s) failed: %s", driver_id, exc)
        raise DependencyUnavailableError("driver-service") from exc
