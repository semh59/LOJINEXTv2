"""OpenRouteService validation adapter."""

from __future__ import annotations

import asyncio
import logging

import httpx
from pydantic import BaseModel

from location_service.config import settings

logger = logging.getLogger(__name__)


class ORSValidationResult(BaseModel):
    """Validation response from ORS."""

    distance: float
    duration: float
    status: str  # VALIDATED, UNVALIDATED, FAILED
    message: str


class ORSValidationClient:
    """Client for ORS validation."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.ors_api_key
        self.base_url = settings.ors_base_url
        self.timeout = settings.provider_timeout_seconds
        self.max_retries = settings.provider_retry_max
        if not self.api_key and settings.enable_ors_validation:
            logger.warning("ORS API key is missing. Adapter will degrade to UNVALIDATED.")

    async def get_validation(
        self, origin_lng: float, origin_lat: float, dest_lng: float, dest_lat: float
    ) -> ORSValidationResult:
        """Fetch an ORS route to validate distance and duration."""
        if not settings.enable_ors_validation:
            return ORSValidationResult(
                distance=0.0,
                duration=0.0,
                status="UNVALIDATED",
                message="ORS validation disabled",
            )

        if not self.api_key:
            return ORSValidationResult(
                distance=0.0,
                duration=0.0,
                status="UNVALIDATED",
                message="ORS API key missing",
            )

        payload = {
            "coordinates": [[origin_lng, origin_lat], [dest_lng, dest_lat]],
            "instructions": False,
        }
        headers = {
            "Authorization": self.api_key,
            "Accept": "application/json, application/geo+json",
            "Content-Type": "application/json",
        }

        max_retries = max(self.max_retries, 0)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(max_retries + 1):
                try:
                    response = await client.post(self.base_url, json=payload, headers=headers)
                except httpx.RequestError as exc:
                    logger.warning("ORS API request error: %s", exc)
                else:
                    if response.status_code == 200:
                        data = response.json()
                        route = data.get("routes", [{}])[0]
                        summary = route.get("summary", {})
                        return ORSValidationResult(
                            distance=summary.get("distance", 0.0),
                            duration=summary.get("duration", 0.0),
                            status="VALIDATED",
                            message="OK",
                        )
                    if response.status_code not in {429, 500, 502, 503, 504}:
                        logger.warning("ORS API non-retryable error %s", response.status_code)
                        break
                    logger.warning("ORS API retryable error %s", response.status_code)

                if attempt < max_retries:
                    await asyncio.sleep(1.0 * (2**attempt))
                    continue
                break

        return ORSValidationResult(
            distance=0.0,
            duration=0.0,
            status="UNVALIDATED",
            message="ORS validation unavailable",
        )
