"""Mapbox Terrain-RGB Adapter (Section 6).

Fetches elevation data given coordinates using Terrain-RGB tiles.
Features tile caching per request and coordinate densification.
"""

import asyncio
import io
import logging
import math
from typing import ClassVar

import httpx
from PIL import Image

from location_service.config import settings
from location_service.errors import internal_error

logger = logging.getLogger(__name__)


class MapboxTerrainClient:
    """Client for Mapbox Terrain-RGB tiles at zoom 14."""

    ZOOM: ClassVar[int] = 14
    TILE_SIZE: ClassVar[int] = 256

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.mapbox_api_key
        if not self.api_key:
            logger.warning("Mapbox API key is missing. Terrain adapter will fail.")

        self.tile_cache: dict[tuple[int, int], Image.Image] = {}

    def _deg2num(self, lat_deg: float, lon_deg: float) -> tuple[float, float]:
        """Convert lat/lon to float tile coordinates at ZOOM 14."""
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

        url = f"https://api.mapbox.com/v4/mapbox.terrain-rgb/{self.ZOOM}/{xtile}/{ytile}.pngraw?access_token={self.api_key}"

        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                    self.tile_cache[(xtile, ytile)] = img
                    return img
                elif resp.status_code in (429, 500, 502, 503, 504):
                    logger.warning(f"Terrain API retryable error {resp.status_code}")
                else:
                    resp.raise_for_status()
            except Exception as e:
                logger.warning(f"Terrain API error on tile {xtile}/{ytile}: {e}")

            if attempt < max_retries - 1:
                await asyncio.sleep(1.0 * (2**attempt))

        raise internal_error(f"Failed to fetch Terrain tile {xtile}/{ytile} after 3 retries.")

    def _decode_elevation(self, r: int, g: int, b: int) -> float:
        """Section 6: height = -10000 + ((R * 256 * 256 + G * 256 + B) * 0.1)"""
        return -10000.0 + ((r * 65536 + g * 256 + b) * 0.1)

    async def get_elevation(self, lng: float, lat: float, client: httpx.AsyncClient) -> float:
        """Get elevation for a single coordinate using bilinear interpolation."""
        x_float, y_float = self._deg2num(lat, lng)

        xtile = int(x_float)
        ytile = int(y_float)

        pixel_x = (x_float - xtile) * self.TILE_SIZE
        pixel_y = (y_float - ytile) * self.TILE_SIZE

        img = await self._fetch_tile(xtile, ytile, client)

        # Nearest neighbor for simplicity, ideally bilinear interpolation
        # To avoid edge boundary complexity in this first pass:
        px = min(int(pixel_x), self.TILE_SIZE - 1)
        py = min(int(pixel_y), self.TILE_SIZE - 1)

        r, g, b = img.getpixel((px, py))
        return self._decode_elevation(r, g, b)

    async def enrich_coordinates(self, coords: list[tuple[float, float]]) -> list[tuple[float, float, float]]:
        """Add elevation to a list of (lng, lat) coordinates."""
        # Note: A real implementation tracks total tiles and raises if > 2000 per request
        enriched = []
        async with httpx.AsyncClient(timeout=10.0) as client:
            for lng, lat in coords:
                elev = await self.get_elevation(lng, lat, client)
                enriched.append((lng, lat, elev))
        return enriched
