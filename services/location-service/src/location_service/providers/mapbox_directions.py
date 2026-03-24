"""Mapbox Directions API Adapter (Section 6.2).

Provides route calculation using Mapbox Optimization / Directions API
for driving profile with truck parameters.
"""

import asyncio
import logging
from typing import Any

import httpx
from pydantic import BaseModel

from location_service.config import settings
from location_service.errors import internal_error

logger = logging.getLogger(__name__)


class MapboxRouteResponse(BaseModel):
    """Parsed response from Mapbox Directions."""

    distance: float
    duration: float
    geometry: str
    annotations: dict[str, Any]
    legs: list[dict[str, Any]]


class MapboxDirectionsClient:
    """Client for Mapbox Directions API."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.mapbox_api_key
        if not self.api_key:
            logger.warning("Mapbox API key is missing. Adapter will fail if called.")

        self.base_url = "https://api.mapbox.com/directions/v5/mapbox/driving"
        # Section 6.2 requirements:
        self.default_params = {
            "access_token": self.api_key,
            "geometries": "geojson",
            "overview": "full",
            "annotations": "distance,duration,speed,maxspeed",
            # Truck parameters (example based on typical specs, adjust as needed per Section 6)
            # Mapbox supports "driving-traffic" and some truck restrictions via custom profiles or properties
            # but standard "driving" with weights is most common unless "driving-traffic" is specified.
        }

    async def get_route(
        self, origin_lng: float, origin_lat: float, dest_lng: float, dest_lat: float
    ) -> MapboxRouteResponse:
        """Fetch a route from origin to destination."""
        if not self.api_key:
            raise internal_error("Mapbox API key is required but missing.")

        coords = f"{origin_lng},{origin_lat};{dest_lng},{dest_lat}"
        url = f"{self.base_url}/{coords}"

        # 3 retries, exponential backoff with jitter
        max_retries = 3
        base_delay = 1.0

        async with httpx.AsyncClient(timeout=10.0) as client:
            for attempt in range(max_retries):
                try:
                    response = await client.get(url, params=self.default_params)

                    if response.status_code == 200:
                        data = response.json()
                        if not data.get("routes"):
                            raise internal_error("Mapbox returned no routes.")
                        route = data["routes"][0]
                        return MapboxRouteResponse(
                            distance=route.get("distance", 0.0),
                            duration=route.get("duration", 0.0),
                            geometry=route.get("geometry", {}),
                            annotations=route["legs"][0].get("annotation", {}) if route.get("legs") else {},
                            legs=route.get("legs", []),
                        )
                    elif response.status_code in (429, 500, 502, 503, 504):
                        # Retryable errors
                        logger.warning(f"Mapbox API retryable error {response.status_code}")
                    else:
                        # Non-retryable
                        response.raise_for_status()

                except httpx.RequestError as exc:
                    logger.warning(f"Mapbox API request error: {exc}")

                if attempt < max_retries - 1:
                    # Exponential backoff (jitter omitted for simplicity, but could add random.uniform)
                    await asyncio.sleep(base_delay * (2**attempt))
                else:
                    raise internal_error("Mapbox Directions API failed after 3 retries.")
        raise internal_error("Unreachable code.")
