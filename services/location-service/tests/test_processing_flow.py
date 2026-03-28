"""Integration tests for the Processing Flow (Section 22)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from location_service.enums import DirectionCode, RunStatus
from location_service.models import (
    LocationPoint,
    ProcessingRun,
    Route,
    RoutePair,
)
from location_service.processing.approval import approve_route_versions
from location_service.processing.bulk import trigger_bulk_refresh
from location_service.processing.export_logic import generate_export_csv_stream
from location_service.processing.import_logic import process_import_csv
from location_service.processing.pipeline import _process_route_pair


@pytest.mark.asyncio
async def test_processing_flow_full_mock():
    """Verify the 30-step processing pipeline using a full mocking strategy."""
    pair_id = uuid.uuid4()
    run_id = uuid.uuid4()
    origin_id = uuid.uuid4()
    dest_id = uuid.uuid4()

    mock_origin = LocationPoint(location_id=origin_id, code="ORIGIN", latitude_6dp=41.0, longitude_6dp=29.0)
    mock_dest = LocationPoint(location_id=dest_id, code="DEST", latitude_6dp=40.0, longitude_6dp=28.0)
    mock_pair = RoutePair(
        route_pair_id=pair_id, pair_code="RP_TEST", origin_location_id=origin_id, destination_location_id=dest_id
    )
    mock_run = ProcessingRun(processing_run_id=run_id, route_pair_id=pair_id, run_status=RunStatus.QUEUED)

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    async def mock_get(model, ident, **kwargs):
        if model == ProcessingRun:
            return mock_run
        if model == RoutePair:
            return mock_pair
        if model == LocationPoint:
            if ident == origin_id:
                return mock_origin
            if ident == dest_id:
                return mock_dest
        return None

    mock_session.get.side_effect = mock_get

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    mock_mb_resp = MagicMock()
    mock_mb_resp.distance = 1000.0
    mock_mb_resp.duration = 600.0
    mock_mb_resp.geometry = {"coordinates": [[29.0, 41.0], [28.0, 40.0]]}
    mock_mb_resp.annotations = {"distance": [1000.0], "speed": [1.66]}

    mock_ors_resp = MagicMock()
    mock_ors_resp.distance = 1005.0
    mock_ors_resp.status = "OK"

    with (
        patch("location_service.processing.pipeline.async_session_factory", return_value=mock_session),
        patch("location_service.processing.pipeline.MapboxDirectionsClient") as mock_mb_cls,
        patch("location_service.processing.pipeline.MapboxTerrainClient") as mock_terrain_cls,
        patch("location_service.processing.pipeline.ORSValidationClient") as mock_ors_cls,
    ):
        mock_mb_cls.return_value.get_route = AsyncMock(return_value=mock_mb_resp)
        mock_ors_cls.return_value.get_validation = AsyncMock(return_value=mock_ors_resp)
        mock_terrain_cls.return_value.enrich_coordinates = AsyncMock(
            return_value=[(29.0, 41.0, 10.0), (28.0, 40.0, 5.0)]
        )

        await _process_route_pair(run_id, pair_id)

        assert mock_run.run_status == RunStatus.SUCCEEDED
        assert mock_pair.pending_forward_version_no == 1
        assert mock_pair.pending_reverse_version_no == 1
        assert mock_session.add.call_count >= 8
        assert mock_session.commit.call_count >= 2


@pytest.mark.asyncio
async def test_approval_flow_promotion():
    """Verify promotion of DRAFT to ACTIVE and SUPERSEDING existing ACTIVE versions."""
    pair_id = uuid.uuid4()
    fwd_route_id = uuid.uuid4()
    rev_route_id = uuid.uuid4()

    mock_pair = RoutePair(
        route_pair_id=pair_id,
        current_active_forward_version_no=1,
        current_active_reverse_version_no=1,
        pending_forward_version_no=2,
        pending_reverse_version_no=2,
    )

    mock_routes = [
        Route(route_id=fwd_route_id, route_pair_id=pair_id, direction=DirectionCode.FORWARD),
        Route(route_id=rev_route_id, route_pair_id=pair_id, direction=DirectionCode.REVERSE),
    ]

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    mock_session.get.return_value = mock_pair

    # Mock routes scalar result
    mock_route_result = MagicMock()
    mock_route_result.scalars.return_value.all.return_value = mock_routes
    mock_session.execute.return_value = mock_route_result

    with patch("location_service.processing.approval.async_session_factory", return_value=mock_session):
        await approve_route_versions(pair_id)

    assert mock_pair.current_active_forward_version_no == 2
    assert mock_pair.current_active_reverse_version_no == 2
    assert mock_pair.pending_forward_version_no is None
    assert mock_pair.pending_reverse_version_no is None
    assert mock_session.commit.called


@pytest.mark.asyncio
async def test_approval_pair_not_found():
    """Confirm ValueError is raised if pair_id does not exist."""
    pair_id = uuid.uuid4()
    mock_session = AsyncMock()
    mock_session.get.return_value = None
    mock_session.__aenter__.return_value = mock_session

    with patch("location_service.processing.approval.async_session_factory", return_value=mock_session):
        with pytest.raises(ValueError, match=f"Route pair {pair_id} not found"):
            await approve_route_versions(pair_id)


@pytest.mark.asyncio
async def test_approval_no_pending_versions():
    """Confirm ValueError is raised if pair has no pending versions."""
    pair_id = uuid.uuid4()
    mock_pair = RoutePair(route_pair_id=pair_id, pending_forward_version_no=None, pending_reverse_version_no=None)
    mock_session = AsyncMock()
    mock_session.get.return_value = mock_pair
    mock_session.__aenter__.return_value = mock_session

    with patch("location_service.processing.approval.async_session_factory", return_value=mock_session):
        with pytest.raises(ValueError, match=f"Route pair {pair_id} has no pending versions to approve"):
            await approve_route_versions(pair_id)


@pytest.mark.asyncio
async def test_bulk_refresh_triggered():
    """Verify bulk refresh triggers multiple processing runs."""
    pair_ids = [uuid.uuid4(), uuid.uuid4()]

    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    # Mock validation of pair IDs
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = pair_ids
    mock_session.execute.return_value = mock_result

    with (
        patch("location_service.processing.bulk.async_session_factory", return_value=mock_session),
        patch("location_service.processing.bulk.trigger_processing", new_callable=AsyncMock) as mock_trigger,
    ):
        count = await trigger_bulk_refresh(pair_ids=pair_ids)

        assert count == 2
        assert mock_trigger.call_count == 2
        calls = [c.kwargs["pair_id"] for c in mock_trigger.call_args_list]
        assert set(calls) == set(pair_ids)


@pytest.mark.asyncio
async def test_bulk_refresh_all_active():
    """Verify global refresh targets all ACTIVE pairs."""
    pair_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]

    # Mock result
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = pair_ids

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    with (
        patch("location_service.processing.bulk.async_session_factory", return_value=mock_session),
        patch("location_service.processing.bulk.trigger_processing", new_callable=AsyncMock) as mock_trigger,
    ):
        count = await trigger_bulk_refresh(pair_ids=None)

        assert count == 3
        assert mock_trigger.call_count == 3


@pytest.mark.asyncio
async def test_bulk_refresh_resilience():
    """Confirm bulk refresh continues even if one trigger fails."""
    pair_ids = [uuid.uuid4(), uuid.uuid4()]

    # Mock result
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = pair_ids

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    with (
        patch("location_service.processing.bulk.async_session_factory", return_value=mock_session),
        patch("location_service.processing.bulk.trigger_processing", new_callable=AsyncMock) as mock_trigger,
    ):
        # First call fails, second succeeds
        mock_trigger.side_effect = [Exception("Simulation failure"), uuid.uuid4()]

        count = await trigger_bulk_refresh(pair_ids=pair_ids)

        # Should count both as "attempted/triggered" logic return
        assert count == 2
        assert mock_trigger.call_count == 2


@pytest.mark.asyncio
async def test_import_csv():
    """Verify CSV import creates RoutePair entries in batch."""
    csv_content = b"origin_code,destination_code\r\nist,ank\r\nank,izmir"

    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    # Mock LocationPoint lookup
    mock_loc_result = MagicMock()
    mock_loc_result.all.return_value = [
        MagicMock(code="IST", location_id=uuid.uuid4()),
        MagicMock(code="ANK", location_id=uuid.uuid4()),
        MagicMock(code="IZMIR", location_id=uuid.uuid4()),
    ]
    mock_session.execute.return_value = mock_loc_result

    with patch("location_service.processing.import_logic.async_session_factory", return_value=mock_session):
        result = await process_import_csv(csv_content)

        assert result.success_count == 2
        assert result.failure_count == 0
        assert mock_session.commit.called


@pytest.mark.asyncio
async def test_import_csv_partial_errors():
    """Verify detailed error reporting for missing points in import."""
    csv_content = b"ist,unknown\r\nmissing1,missing2"

    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    # Mock LocationPoint lookup - only 'IST' exists
    mock_loc_result = MagicMock()
    mock_loc_result.all.return_value = [
        MagicMock(code="IST", location_id=uuid.uuid4()),
    ]
    mock_session.execute.return_value = mock_loc_result

    with patch("location_service.processing.import_logic.async_session_factory", return_value=mock_session):
        result = await process_import_csv(csv_content)

        assert result.success_count == 0
        assert result.failure_count == 2
        assert "Missing points" in result.errors[0][1]


@pytest.mark.asyncio
async def test_export_streaming():
    """Verify CSV export streams data correctly."""
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    # Mock streaming result
    class MockIter:
        def __init__(self):
            self.data = [
                MagicMock(
                    route_pair_id=uuid.uuid4(),
                    pair_code="RP1",
                    pair_status="ACTIVE",
                    origin_code="IST",
                    destination_code="ANK",
                    current_active_forward_version_no=1,
                    current_active_reverse_version_no=1,
                )
            ]
            self.index = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.index >= len(self.data):
                raise StopAsyncIteration
            val = self.data[self.index]
            self.index += 1
            return val

    mock_session.stream.return_value = MockIter()

    with patch("location_service.processing.export_logic.async_session_factory", return_value=mock_session):
        chunks = []
        async for chunk in generate_export_csv_stream():
            chunks.append(chunk)

        assert len(chunks) >= 2  # Header + 1 row
        assert "pair_id,pair_code" in chunks[0]
        assert "RP1" in chunks[1]
        assert "IST" in chunks[1]
