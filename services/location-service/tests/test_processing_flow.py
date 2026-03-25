"""Integration tests for the Processing Flow (Section 22)."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from location_service.models import LocationPoint, RoutePair, RouteSegment, RouteVersion


@pytest.mark.asyncio
async def test_calculate_workflow_success(client: AsyncClient, test_session):
    # 1. Setup Data
    p1 = LocationPoint(
        location_id="00000000-0000-0000-0000-000000000001",
        code="IST_HLP",
        name_tr="İstanbul Havalimanı",
        name_en="Istanbul Airport",
        latitude_6dp=41.275,
        longitude_6dp=28.751,
        normalized_name_tr="istanbul havalimani",
        normalized_name_en="istanbul airport",
    )
    p2 = LocationPoint(
        location_id="00000000-0000-0000-0000-000000000002",
        code="SAW_HLP",
        name_tr="Sabiha Gökçen",
        name_en="Sabiha Gokcen",
        latitude_6dp=40.898,
        longitude_6dp=29.309,
        normalized_name_tr="sabiha gokcen",
        normalized_name_en="sabiha gokcen",
    )
    pair = RoutePair(
        route_pair_id="00000000-0000-0000-0000-000000000011",
        pair_code="RP_" + "A" * 26,
        origin_location_id=p1.location_id,
        destination_location_id=p2.location_id,
        pair_status="DRAFT",
    )
    test_session.add_all([p1, p2, pair])
    await test_session.commit()

    # 2. Mock Providers
    mock_mb_resp = AsyncMock()
    mock_mb_resp.distance = 80000.0
    mock_mb_resp.duration = 3600.0
    mock_mb_resp.geometry = {"coordinates": [[28.751, 41.275], [29.309, 40.898]]}
    mock_mb_resp.annotations = {
        "distance": [80000.0],
        "duration": [3600.0],
        "speed": [22.2],  # ~80kph
    }

    mock_ors_resp = AsyncMock()
    mock_ors_resp.status = "VALIDATED"
    mock_ors_resp.distance = 79500.0

    mock_enrich = AsyncMock(return_value=[(28.751, 41.275, 100.0), (29.309, 40.898, 50.0)])

    with (
        patch("location_service.processing.pipeline.MapboxDirectionsClient.get_route", return_value=mock_mb_resp),
        patch("location_service.processing.pipeline.MapboxTerrainClient.enrich_coordinates", side_effect=mock_enrich),
        patch("location_service.processing.pipeline.ORSValidationClient.get_validation", return_value=mock_ors_resp),
    ):
        # 3. Trigger API
        resp = await client.post(f"/v1/pairs/{pair.route_pair_id}/calculate")
        assert resp.status_code == 202
        data = resp.json()
        run_id = data["run_id"]

        # 4. Wait for processing (polling)
        max_wait = 10
        for _ in range(max_wait):
            await asyncio.sleep(0.5)
            status_resp = await client.get(f"/v1/pairs/processing-runs/{run_id}")
            if status_resp.json()["run_status"] == "SUCCEEDED":
                break
        else:
            pytest.fail("Processing timed out")

    # 5. Verify Results
    # Check Route Versions
    from sqlalchemy import select

    vers = (
        (await test_session.execute(select(RouteVersion).where(RouteVersion.processing_run_id == run_id)))
        .scalars()
        .all()
    )
    assert len(vers) == 2  # Forward and Reverse

    # Check Segments
    segs = (
        (await test_session.execute(select(RouteSegment).where(RouteSegment.route_id == vers[0].route_id)))
        .scalars()
        .all()
    )
    assert len(segs) > 0

    # Ensure Pair is updated
    await test_session.refresh(pair)
    assert pair.pending_forward_version_no == 1
    assert pair.pending_reverse_version_no == 1
