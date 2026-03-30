"""Unit tests for provider adapters and provider config wiring."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from location_service.config import settings
from location_service.providers.mapbox_directions import MapboxDirectionsClient
from location_service.providers.mapbox_terrain import MapboxTerrainClient
from location_service.providers.ors_validation import ORSValidationClient


@pytest.mark.asyncio
async def test_mapbox_directions_success_parses_geojson() -> None:
    client = MapboxDirectionsClient(api_key="test-key")

    mock_resp = httpx.Response(
        200,
        json={
            "routes": [
                {
                    "distance": 1500.5,
                    "duration": 300.2,
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[10.0, 10.0], [20.0, 20.0]],
                    },
                    "legs": [{"annotation": {"speed": [10, 15], "maxspeed": [{"speed": 70, "unit": "km/h"}]}}],
                }
            ]
        },
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp

        result = await client.get_route(10.0, 10.0, 20.0, 20.0)

    assert result.distance == 1500.5
    assert result.duration == 300.2
    assert result.geometry.type == "LineString"
    assert result.geometry.coordinates == [(10.0, 10.0), (20.0, 20.0)]
    assert result.annotations["speed"] == [10, 15]
    mock_get.assert_called_once()
    assert mock_get.await_args.kwargs["params"]["steps"] == "true"


@pytest.mark.asyncio
async def test_ors_validation_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_ors_validation", True)
    monkeypatch.setattr(settings, "provider_timeout_ms", 2500)
    monkeypatch.setattr(settings, "provider_retry_max", 2)

    client = ORSValidationClient(api_key="test-ors-key")

    mock_resp = httpx.Response(
        200,
        json={
            "routes": [
                {
                    "summary": {"distance": 1450.0, "duration": 290.0},
                }
            ]
        },
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        result = await client.get_validation(10.0, 10.0, 20.0, 20.0)

    assert client.timeout == 2.5
    assert client.max_retries == 2
    assert result.status == "VALIDATED"
    assert result.distance == 1450.0
    assert result.duration == 290.0
    mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_ors_validation_disabled_skips_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_ors_validation", False)
    client = ORSValidationClient(api_key="test-ors-key")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        result = await client.get_validation(10.0, 10.0, 20.0, 20.0)

    assert result.status == "UNVALIDATED"
    assert result.message == "ORS validation disabled"
    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_ors_validation_missing_key_degrades(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "enable_ors_validation", True)
    monkeypatch.setattr(settings, "ors_api_key", "")
    client = ORSValidationClient(api_key="")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        result = await client.get_validation(10.0, 10.0, 20.0, 20.0)

    assert result.status == "UNVALIDATED"
    assert result.distance == 0.0
    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_mapbox_terrain_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    from PIL import Image

    monkeypatch.setattr(settings, "provider_timeout_ms", 3100)
    monkeypatch.setattr(settings, "provider_retry_max", 4)
    client = MapboxTerrainClient(api_key="test-terrain-key")

    img = Image.new("RGB", (256, 256), color=(10, 20, 30))
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="PNG")

    mock_resp = httpx.Response(200, content=img_byte_arr.getvalue())

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        async with httpx.AsyncClient() as ac:
            elev = await client.get_elevation(28.9784, 41.0082, ac)

    assert client.timeout == 3.1
    assert client.max_retries == 4
    assert elev == 56051.0
    mock_get.assert_called_once()


def test_mapbox_directions_uses_configured_timeout_and_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "provider_timeout_ms", 4100)
    monkeypatch.setattr(settings, "provider_retry_max", 5)
    monkeypatch.setattr(settings, "mapbox_directions_base_url", "https://example.com/directions/v5")

    client = MapboxDirectionsClient(api_key="test-key")

    assert client.timeout == 4.1
    assert client.max_retries == 5
    assert client.base_url == "https://example.com/directions/v5/mapbox/driving"
