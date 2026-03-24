"""Unit tests for Provider Adapters (Section 6)."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from location_service.providers.mapbox_directions import MapboxDirectionsClient
from location_service.providers.mapbox_terrain import MapboxTerrainClient
from location_service.providers.ors_validation import ORSValidationClient


@pytest.mark.asyncio
async def test_mapbox_directions_success():
    client = MapboxDirectionsClient(api_key="test_key")

    mock_resp = httpx.Response(
        200,
        json={
            "routes": [
                {
                    "distance": 1500.5,
                    "duration": 300.2,
                    "geometry": "encoded_polyline",
                    "legs": [{"annotation": {"speed": [10, 15]}}],
                }
            ]
        },
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp

        result = await client.get_route(10.0, 10.0, 20.0, 20.0)
        assert result.distance == 1500.5
        assert result.duration == 300.2
        assert result.geometry == "encoded_polyline"
        assert result.annotations == {"speed": [10, 15]}
        mock_get.assert_called_once()


@pytest.mark.asyncio
async def test_ors_validation_success():
    client = ORSValidationClient(api_key="test_ors_key")

    mock_resp = httpx.Response(
        200,
        json={
            "routes": [
                {
                    "summary": {"distance": 1450.0, "duration": 290.0},
                    "bbox": [10.0, 10.0, 20.0, 20.0],  # minX, minY, maxX, maxY
                }
            ]
        },
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        result = await client.get_validation(10.0, 10.0, 20.0, 20.0)
        assert result.status == "VALIDATED"
        assert result.distance == 1450.0
        assert result.end_location == (20.0, 20.0)
        mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_ors_validation_missing_key():
    client = ORSValidationClient(api_key="")
    # Should degrade gracefully
    result = await client.get_validation(10.0, 10.0, 20.0, 20.0)
    assert result.status == "UNVALIDATED"
    assert result.distance == 0.0


@pytest.mark.asyncio
async def test_mapbox_terrain_success():
    import io

    from PIL import Image

    client = MapboxTerrainClient(api_key="test_terrain_key")

    # Create a 256x256 image with color (10, 20, 30)
    img = Image.new("RGB", (256, 256), color=(10, 20, 30))
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="PNG")

    mock_resp = httpx.Response(200, content=img_byte_arr.getvalue())

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp

        # Expected calculation:
        # height = -10000 + ((10 * 65536 + 20 * 256 + 30) * 0.1)
        # R=10: 655360, G=20: 5120, B=30 -> 660510 * 0.1 = 66051.0
        # height = -10000 + 66051.0 = 56051.0

        async with httpx.AsyncClient() as ac:
            elev = await client.get_elevation(28.9784, 41.0082, ac)

        assert elev == 56051.0
        mock_get.assert_called_once()
