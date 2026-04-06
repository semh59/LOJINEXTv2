"""Mapbox Terrain-RGB adapter."""

from __future__ import annotations

import asyncio
import io
import logging
import math
from typing import ClassVar

import httpx
from PIL import Image

from location_service.config import settings
from location_service.errors import internal_error
from location_service.observability import correlation_id

logger = logging.getLogger(__name__)


class MapboxTerrainClient:
    """Client for Mapbox Terrain-RGB tiles at zoom 14."""

    ZOOM: ClassVar[int] = 14
    TILE_SIZE: ClassVar[int] = 256

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.mapbox_api_key
        self.base_url = settings.mapbox_raster_base_url.rstrip("/")
        self.timeout = settings.provider_timeout_seconds
        self.max_retries = settings.provider_retry_max
        if not self.api_key:
            logger.warning("Mapbox API key is missing. Terrain adapter will fail.")

        self.tile_cache: dict[tuple[int, int], Image.Image] = {}

    def _deg2num(self, lat_deg: float, lon_deg: float) -> tuple[float, float]:
        """Convert lat/lon to float tile coordinates at zoom 14."""
        lat_rad = math.radians(lat_deg)
        n = 2.0**self.ZOOM
        x = (lon_deg + 180.0) / 360.0 * n
        y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
        return x, y

    async def _fetch_tile(self, xtile: int, ytile: int, client: httpx.AsyncClient) -> Image.Image:
        """Fetch a single Terrain-RGB tile."""
        if (xtile, ytile) in self.tile_cache:
            return self.tile_cache[(xtile, ytile)]

        if not self.api_key:
            raise internal_error("Mapbox API key is missing.")

        url = f"{self.base_url}/mapbox.terrain-rgb/{self.ZOOM}/{xtile}/{ytile}.pngraw?access_token={self.api_key}"

        max_retries = max(self.max_retries, 0)
        headers = {}
        if c_id := correlation_id.get():
            headers["X-Correlation-ID"] = c_id

        for attempt in range(max_retries + 1):
            try:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                    self.tile_cache[(xtile, ytile)] = img
                    return img
                if resp.status_code in {429, 500, 502, 503, 504}:
                    logger.warning("Terrain API retryable error %s", resp.status_code)
                else:
                    logger.warning("Terrain API non-retryable error %s", resp.status_code)
                    raise internal_error("Mapbox Terrain API returned a non-retryable error.")
            except httpx.RequestError as exc:
                logger.warning("Terrain API request error on tile %s/%s: %s", xtile, ytile, exc)

            if attempt < max_retries:
                await asyncio.sleep(1.0 * (2**attempt))
                continue
            raise internal_error(f"Failed to fetch Terrain tile {xtile}/{ytile} after retry exhaustion.")

        raise internal_error(f"Failed to fetch Terrain tile {xtile}/{ytile}.")

    def _decode_elevation(self, r: int, g: int, b: int) -> float:
        """Decode Terrain-RGB pixel values into meters above sea level."""
        return -10000.0 + ((r * 65536 + g * 256 + b) * 0.1)

    async def get_elevation(self, lng: float, lat: float, client: httpx.AsyncClient) -> float:
        """Get elevation for a single coordinate using nearest-neighbor lookup."""
        x_float, y_float = self._deg2num(lat, lng)
        xtile = int(x_float)
        ytile = int(y_float)
        pixel_x = (x_float - xtile) * self.TILE_SIZE
        pixel_y = (y_float - ytile) * self.TILE_SIZE

        img = await self._fetch_tile(xtile, ytile, client)
        px = min(int(pixel_x), self.TILE_SIZE - 1)
        py = min(int(pixel_y), self.TILE_SIZE - 1)

        pixel = img.getpixel((px, py))
        if not isinstance(pixel, (tuple, list)) or len(pixel) < 3:
            raise internal_error("Invalid pixel format from terrain tile.")

        r, g, b = pixel[:3]
        return self._decode_elevation(r, g, b)

    async def enrich_coordinates(self, coords: list[tuple[float, float]]) -> list[tuple[float, float, float]]:
        """Add elevation to a list of (lng, lat) coordinates."""
        enriched: list[tuple[float, float, float]] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for lng, lat in coords:
                elev = await self.get_elevation(lng, lat, client)
                enriched.append((lng, lat, elev))
        return enriched
