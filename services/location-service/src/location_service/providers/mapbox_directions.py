"""Mapbox Directions API adapter."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field

from location_service.config import settings
from location_service.errors import internal_error

logger = logging.getLogger(__name__)


class MapboxGeometry(BaseModel):
    """GeoJSON LineString geometry returned by Mapbox Directions."""

    type: str = Field(default="LineString")
    coordinates: list[tuple[float, float]]


class MapboxRouteResponse(BaseModel):
    """Parsed response from Mapbox Directions."""

    distance: float
    duration: float
    geometry: MapboxGeometry
    annotations: dict[str, Any]
    legs: list[dict[str, Any]]


class MapboxDirectionsClient:
    """Client for Mapbox Directions API."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.mapbox_api_key
        self.base_url = settings.mapbox_directions_base_url.rstrip("/") + "/mapbox/driving"
        self.timeout = settings.provider_timeout_seconds
        self.max_retries = settings.provider_retry_max
        if not self.api_key:
            logger.warning("Mapbox API key is missing. Adapter will fail if called.")

        self.default_params = {
            "access_token": self.api_key,
            "geometries": "geojson",
            "overview": "full",
            "annotations": "distance,duration,speed,maxspeed",
        }

    async def get_route(
        self, origin_lng: float, origin_lat: float, dest_lng: float, dest_lat: float
    ) -> MapboxRouteResponse:
        """Fetch a route from origin to destination."""
        if not self.api_key:
            raise internal_error("Mapbox API key is required but missing.")

        coords = f"{origin_lng},{origin_lat};{dest_lng},{dest_lat}"
        url = f"{self.base_url}/{coords}"
        max_retries = max(self.max_retries, 0)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for attempt in range(max_retries + 1):
                try:
                    response = await client.get(url, params=self.default_params)

                    if response.status_code == 200:
                        data = response.json()
                        if not data.get("routes"):
                            raise internal_error("Mapbox Directions API returned no routes.")
                        route = data["routes"][0]
                        return MapboxRouteResponse(
                            distance=route.get("distance", 0.0),
                            duration=route.get("duration", 0.0),
                            geometry=route.get("geometry", {}),
                            annotations=route["legs"][0].get("annotation", {}) if route.get("legs") else {},
                            legs=route.get("legs", []),
                        )

                    if response.status_code in {429, 500, 502, 503, 504}:
                        logger.warning("Mapbox API retryable error %s", response.status_code)
                    else:
                        logger.warning("Mapbox API non-retryable error %s", response.status_code)
                        raise internal_error("Mapbox Directions API returned a non-retryable error.")

                except httpx.RequestError as exc:
                    logger.warning("Mapbox API request error: %s", exc)

                if attempt < max_retries:
                    await asyncio.sleep(1.0 * (2**attempt))
                    continue
                raise internal_error("Mapbox Directions API failed after retry exhaustion.")

        raise internal_error("Mapbox Directions API failed unexpectedly.")
