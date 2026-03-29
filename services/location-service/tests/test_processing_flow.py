"""Mock-based tests for processing, approval, and bulk refresh flows."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import ProgrammingError

from location_service.enums import DirectionCode, PairStatus, RunStatus
from location_service.models import LocationPoint, ProcessingRun, Route, RoutePair
from location_service.processing.approval import approve_route_versions, discard_route_versions
from location_service.processing.bulk import trigger_bulk_refresh
from location_service.processing.pipeline import _process_route_pair, recover_processing_runs


@pytest.mark.asyncio
async def test_processing_flow_full_mock() -> None:
    pair_id = uuid.uuid4()
    run_id = uuid.uuid4()
    origin_id = uuid.uuid4()
    dest_id = uuid.uuid4()

    mock_origin = LocationPoint(location_id=origin_id, code="ORIGIN", latitude_6dp=41.0, longitude_6dp=29.0)
    mock_dest = LocationPoint(location_id=dest_id, code="DEST", latitude_6dp=40.0, longitude_6dp=28.0)
    mock_pair = RoutePair(
        route_pair_id=pair_id,
        pair_code="RP_TEST",
        origin_location_id=origin_id,
        destination_location_id=dest_id,
        pair_status=PairStatus.DRAFT,
        row_version=1,
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
    mock_mb_resp.geometry = SimpleNamespace(coordinates=[(29.0, 41.0), (28.0, 40.0)])
    mock_mb_resp.annotations = {
        "distance": [1000.0],
        "speed": [1.66],
        "maxspeed": [{"speed": 70, "unit": "km/h"}],
    }

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
    assert mock_pair.forward_route_id is not None
    assert mock_pair.reverse_route_id is not None
    assert mock_pair.row_version == 2
    assert mock_session.add.call_count >= 8
    assert mock_session.commit.call_count >= 2


@pytest.mark.asyncio
async def test_recover_processing_runs_requeues_queued_and_stale_running() -> None:
    queued_run = ProcessingRun(
        processing_run_id=uuid.uuid4(),
        route_pair_id=uuid.uuid4(),
        run_status=RunStatus.QUEUED,
        trigger_type="INITIAL_CALCULATE",
        created_at_utc=datetime.now(UTC),
    )
    stale_run = ProcessingRun(
        processing_run_id=uuid.uuid4(),
        route_pair_id=uuid.uuid4(),
        run_status=RunStatus.RUNNING,
        trigger_type="INITIAL_CALCULATE",
        started_at_utc=datetime.now(UTC) - timedelta(minutes=45),
        created_at_utc=datetime.now(UTC) - timedelta(minutes=45),
    )
    fresh_run = ProcessingRun(
        processing_run_id=uuid.uuid4(),
        route_pair_id=uuid.uuid4(),
        run_status=RunStatus.RUNNING,
        trigger_type="INITIAL_CALCULATE",
        started_at_utc=datetime.now(UTC) - timedelta(minutes=5),
        created_at_utc=datetime.now(UTC) - timedelta(minutes=5),
    )

    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None
    result = MagicMock()
    result.scalars.return_value.all.return_value = [queued_run, stale_run, fresh_run]
    mock_session.execute.return_value = result

    dispatched: list[tuple[uuid.UUID, uuid.UUID]] = []

    with (
        patch("location_service.processing.pipeline.async_session_factory", return_value=mock_session),
        patch(
            "location_service.processing.pipeline._dispatch_processing_task",
            side_effect=lambda run_id, pair_id: dispatched.append((run_id, pair_id)),
        ),
    ):
        recovered = await recover_processing_runs()

    assert recovered == 2
    assert queued_run.run_status == RunStatus.QUEUED
    assert stale_run.run_status == RunStatus.QUEUED
    assert stale_run.started_at_utc is None
    assert fresh_run.run_status == RunStatus.RUNNING
    assert dispatched == [
        (queued_run.processing_run_id, queued_run.route_pair_id),
        (stale_run.processing_run_id, stale_run.route_pair_id),
    ]


@pytest.mark.asyncio
async def test_recover_processing_runs_skips_before_schema_exists() -> None:
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None
    mock_session.execute.side_effect = ProgrammingError(
        "SELECT ... FROM processing_runs",
        {},
        Exception('relation "processing_runs" does not exist'),
    )

    with patch("location_service.processing.pipeline.async_session_factory", return_value=mock_session):
        recovered = await recover_processing_runs()

    assert recovered == 0


@pytest.mark.asyncio
async def test_approval_flow_promotion_increments_row_version() -> None:
    pair_id = uuid.uuid4()
    forward_route_id = uuid.uuid4()
    reverse_route_id = uuid.uuid4()

    mock_pair = RoutePair(
        route_pair_id=pair_id,
        current_active_forward_version_no=1,
        current_active_reverse_version_no=1,
        pending_forward_version_no=2,
        pending_reverse_version_no=2,
        pair_status=PairStatus.DRAFT,
        row_version=5,
    )

    mock_routes = [
        Route(route_id=forward_route_id, route_pair_id=pair_id, direction=DirectionCode.FORWARD),
        Route(route_id=reverse_route_id, route_pair_id=pair_id, direction=DirectionCode.REVERSE),
    ]

    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None
    mock_session.get.return_value = mock_pair

    mock_route_result = MagicMock()
    mock_route_result.scalars.return_value.all.return_value = mock_routes
    mock_session.execute.return_value = mock_route_result

    with patch("location_service.processing.approval.async_session_factory", return_value=mock_session):
        await approve_route_versions(pair_id)

    assert mock_pair.forward_route_id == forward_route_id
    assert mock_pair.reverse_route_id == reverse_route_id
    assert mock_pair.current_active_forward_version_no == 2
    assert mock_pair.current_active_reverse_version_no == 2
    assert mock_pair.pending_forward_version_no is None
    assert mock_pair.pending_reverse_version_no is None
    assert mock_pair.pair_status == PairStatus.ACTIVE
    assert mock_pair.row_version == 6
    assert mock_session.commit.called


@pytest.mark.asyncio
async def test_discard_flow_clears_pending_and_increments_row_version() -> None:
    pair_id = uuid.uuid4()
    forward_route_id = uuid.uuid4()
    reverse_route_id = uuid.uuid4()

    mock_pair = RoutePair(
        route_pair_id=pair_id,
        pending_forward_version_no=3,
        pending_reverse_version_no=4,
        pair_status=PairStatus.DRAFT,
        row_version=7,
    )
    mock_routes = [
        Route(route_id=forward_route_id, route_pair_id=pair_id, direction=DirectionCode.FORWARD),
        Route(route_id=reverse_route_id, route_pair_id=pair_id, direction=DirectionCode.REVERSE),
    ]

    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None
    mock_session.get.return_value = mock_pair

    mock_route_result = MagicMock()
    mock_route_result.scalars.return_value.all.return_value = mock_routes
    mock_session.execute.return_value = mock_route_result

    with patch("location_service.processing.approval.async_session_factory", return_value=mock_session):
        await discard_route_versions(pair_id)

    assert mock_pair.pending_forward_version_no is None
    assert mock_pair.pending_reverse_version_no is None
    assert mock_pair.row_version == 8
    assert mock_session.commit.called


@pytest.mark.asyncio
async def test_approval_pair_not_found() -> None:
    pair_id = uuid.uuid4()
    mock_session = AsyncMock()
    mock_session.get.return_value = None
    mock_session.__aenter__.return_value = mock_session

    with patch("location_service.processing.approval.async_session_factory", return_value=mock_session):
        with pytest.raises(ValueError, match=f"Route pair {pair_id} not found"):
            await approve_route_versions(pair_id)


@pytest.mark.asyncio
async def test_approval_no_pending_versions() -> None:
    pair_id = uuid.uuid4()
    mock_pair = RoutePair(
        route_pair_id=pair_id,
        pending_forward_version_no=None,
        pending_reverse_version_no=None,
        pair_status=PairStatus.DRAFT,
        row_version=1,
    )
    mock_session = AsyncMock()
    mock_session.get.return_value = mock_pair
    mock_session.__aenter__.return_value = mock_session

    with patch("location_service.processing.approval.async_session_factory", return_value=mock_session):
        with pytest.raises(ValueError, match=f"Route pair {pair_id} has no pending versions to approve"):
            await approve_route_versions(pair_id)


@pytest.mark.asyncio
async def test_bulk_refresh_triggered() -> None:
    pair_ids = [uuid.uuid4(), uuid.uuid4()]
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

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
    calls = [call.kwargs["pair_id"] for call in mock_trigger.call_args_list]
    assert set(calls) == set(pair_ids)


@pytest.mark.asyncio
async def test_bulk_refresh_all_active() -> None:
    pair_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
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
async def test_bulk_refresh_resilience() -> None:
    pair_ids = [uuid.uuid4(), uuid.uuid4()]
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
        mock_trigger.side_effect = [Exception("Simulation failure"), uuid.uuid4()]
        count = await trigger_bulk_refresh(pair_ids=pair_ids)

    assert count == 2
    assert mock_trigger.call_count == 2
