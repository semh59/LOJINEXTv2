"""OpenRouteService Validation Adapter (Section 6).

Provides secondary validation for Mapbox routes.
"""

import logging

import httpx
from pydantic import BaseModel

from location_service.config import settings

logger = logging.getLogger(__name__)


class ORSValidationResult(BaseModel):
    """Validation response from ORS."""

    distance: float
    duration: float
    end_location: tuple[float, float]
    status: str  # "VALIDATED", "UNVALIDATED", "FAILED"
    message: str


class ORSValidationClient:
    """Client for ORS validation."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or getattr(settings, "ors_api_key", None)
        if not self.api_key:
            logger.warning("ORS API key is missing. Adapter will degrade to UNVALIDATED.")

        self.base_url = "https://api.openrouteservice.org/v2/directions/driving-hgv"

    async def get_validation(
        self, origin_lng: float, origin_lat: float, dest_lng: float, dest_lat: float
    ) -> ORSValidationResult:
        """Fetch ORS route to validate distance/duration."""
        if not self.api_key:
            return ORSValidationResult(
                distance=0.0,
                duration=0.0,
                end_location=(0.0, 0.0),
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

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(self.base_url, json=payload, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    route = data.get("routes", [{}])[0]
                    summary = route.get("summary", {})
                    # Need end location, bounding box or last point
                    bbox = route.get("bbox", [0, 0, 0, 0])
                    end_loc = (bbox[2], bbox[3])  # Approximation

                    return ORSValidationResult(
                        distance=summary.get("distance", 0.0),
                        duration=summary.get("duration", 0.0),
                        end_location=end_loc,
                        status="VALIDATED",
                        message="OK",
                    )
                else:
                    logger.warning(f"ORS API error {response.status_code}: {response.text}")
                    return ORSValidationResult(
                        distance=0.0,
                        duration=0.0,
                        end_location=(0.0, 0.0),
                        status="UNVALIDATED",
                        message=f"ORS API error {response.status_code}",
                    )
            except httpx.RequestError as exc:
                logger.warning(f"ORS API request error: {exc}")
                return ORSValidationResult(
                    distance=0.0,
                    duration=0.0,
                    end_location=(0.0, 0.0),
                    status="UNVALIDATED",
                    message=f"ORS Request error: {exc}",
                )
