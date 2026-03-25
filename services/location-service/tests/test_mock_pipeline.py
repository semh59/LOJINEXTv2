"""Manual verification of pipeline logic without Docker."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from location_service.enums import PairStatus, RunStatus, TriggerType
from location_service.models import LocationPoint, ProcessingRun, RoutePair
from location_service.processing.pipeline import _process_route_pair


@pytest.mark.asyncio
async def test_manual_verify_logic():
    # 1. Setup session mock
    session_mock = AsyncMock()

    # Mock data
    run_id = uuid.uuid4()
    pair_id = uuid.uuid4()

    run = ProcessingRun(
        processing_run_id=run_id, run_status=RunStatus.QUEUED, trigger_type=TriggerType.INITIAL_CALCULATE
    )
    origin_id = uuid.uuid4()
    dest_id = uuid.uuid4()
    pair = RoutePair(
        route_pair_id=pair_id,
        origin_location_id=origin_id,
        destination_location_id=dest_id,
        pair_code="RP_" + "A" * 26,
        pair_status=PairStatus.DRAFT,
    )
    origin = LocationPoint(
        location_id=origin_id,
        code="ORG",
        name_tr="O",
        name_en="O",
        normalized_name_tr="O",
        normalized_name_en="O",
        latitude_6dp=0,
        longitude_6dp=0,
    )
    dest = LocationPoint(
        location_id=dest_id,
        code="DST",
        name_tr="D",
        name_en="D",
        normalized_name_tr="D",
        normalized_name_en="D",
        latitude_6dp=1,
        longitude_6dp=1,
    )

    # Mock session.get side effects
    async def mock_get(model, pk):
        if model == ProcessingRun:
            return run
        if model == RoutePair:
            return pair
        if model == LocationPoint:
            if pk == origin_id:
                return origin
            if pk == dest_id:
                return dest
        return None

    session_mock.get.side_effect = mock_get
    from unittest.mock import MagicMock

    res_mock = MagicMock()
    res_mock.scalar_one_or_none.return_value = None
    session_mock.execute = AsyncMock(return_value=res_mock)

    # 2. Mock Provider Clients
    mock_mb_resp = AsyncMock()
    mock_mb_resp.distance = 1000.0
    mock_mb_resp.duration = 600.0
    mock_mb_resp.geometry = {"coordinates": [[0, 0], [1, 1]]}
    mock_mb_resp.annotations = {"distance": [1000.0], "duration": [600.0], "speed": [1.6]}

    mock_ors_resp = AsyncMock()
    mock_ors_resp.status = "VALIDATED"
    mock_ors_resp.distance = 1000.0

    mock_enrich = AsyncMock(return_value=[(0, 0, 0), (1, 1, 0)])

    # 3. Path and Execute
    with (
        patch(
            "location_service.processing.pipeline.async_session_factory",
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=session_mock)),
        ),
        patch("location_service.processing.pipeline.MapboxDirectionsClient.get_route", return_value=mock_mb_resp),
        patch("location_service.processing.pipeline.MapboxTerrainClient.enrich_coordinates", side_effect=mock_enrich),
        patch("location_service.processing.pipeline.ORSValidationClient.get_validation", return_value=mock_ors_resp),
    ):
        await _process_route_pair(run_id, pair_id)

        # Verify run status
        assert run.run_status == RunStatus.SUCCEEDED
