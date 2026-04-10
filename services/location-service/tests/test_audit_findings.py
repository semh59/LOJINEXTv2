"""Mock-based audit regression tests for critical contract behaviors."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import SUPER_ADMIN_HEADERS
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from ulid import ULID

from location_service.auth import (
    AuthContext,
    super_admin_auth_dependency,
    trip_service_auth_dependency,
    user_auth_dependency,
)
from location_service.domain.normalization import normalize_en, normalize_tr
from location_service.errors import ProblemDetailError, problem_detail_handler, validation_exception_handler
from location_service.main import create_app
from location_service.models import LocationPoint, ProcessingRun, RoutePair
from location_service.processing.approval import approve_route_versions
from location_service.processing.pipeline import trigger_processing
from location_service.routers.pairs import router as pairs_router
from location_service.routers.points import router as points_router
from location_service.routers.processing import router as processing_router
from location_service.schemas import CalculateRequest, PairUpdateRequest, PointUpdate


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(ProblemDetailError, problem_detail_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.include_router(points_router)
    app.include_router(pairs_router)
    app.include_router(processing_router)
    return app


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = None
    return session


@pytest.fixture
def app_client(mock_session):
    app = _make_app()

    async def override_get_db():
        yield mock_session

    from location_service.database import get_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[user_auth_dependency] = lambda: AuthContext(actor_id="admin-test-001", role="ADMIN")
    app.dependency_overrides[super_admin_auth_dependency] = lambda: AuthContext(
        actor_id="super-admin-001",
        role="SUPER_ADMIN",
    )
    return TestClient(app, raise_server_exceptions=False)


def test_schema_guards_forbid_removed_fields() -> None:
    assert "latitude_6dp" not in PointUpdate.model_fields
    assert "longitude_6dp" not in PointUpdate.model_fields
    assert "is_active" not in PairUpdateRequest.model_fields
    assert not CalculateRequest.model_fields


def test_patch_point_requires_if_match(app_client, mock_session) -> None:
    location_id = str(ULID())
    mock_point = MagicMock(spec=LocationPoint)
    mock_point.location_id = location_id
    mock_point.row_version = 1
    mock_point.is_active = True
    mock_point.name_tr = "Eski"
    mock_point.name_en = "Old"
    mock_point.normalized_name_tr = "ESKI"
    mock_point.normalized_name_en = "OLD"

    result = MagicMock()
    result.scalar_one_or_none.return_value = mock_point
    mock_session.execute = AsyncMock(return_value=result)

    response = app_client.patch(f"/api/v1/points/{location_id}", json={"name_tr": "Yeni"})
    assert response.status_code == 428
    assert response.json()["code"] == "LOCATION_IF_MATCH_REQUIRED"


def test_patch_point_etag_mismatch(app_client, mock_session) -> None:
    location_id = str(ULID())
    mock_point = MagicMock(spec=LocationPoint)
    mock_point.location_id = location_id
    mock_point.row_version = 5
    mock_point.is_active = True
    mock_point.name_tr = "Eski"
    mock_point.name_en = "Old"
    mock_point.normalized_name_tr = "ESKI"
    mock_point.normalized_name_en = "OLD"

    result = MagicMock()
    result.scalar_one_or_none.return_value = mock_point
    mock_session.execute = AsyncMock(return_value=result)

    response = app_client.patch(
        f"/api/v1/points/{location_id}",
        json={"name_tr": "Yeni"},
        headers={"If-Match": '"3"'},
    )
    assert response.status_code == 412
    assert response.json()["code"] == "LOCATION_POINT_VERSION_MISMATCH"


def test_deactivate_point_blocked_by_active_pair(app_client, mock_session) -> None:
    location_id = str(ULID())
    mock_point = MagicMock(spec=LocationPoint)
    mock_point.location_id = location_id
    mock_point.row_version = 2
    mock_point.is_active = True
    mock_point.name_tr = "Point"
    mock_point.name_en = "Point"
    mock_point.normalized_name_tr = normalize_tr("Point")
    mock_point.normalized_name_en = normalize_en("Point")

    blocking_pair = MagicMock(spec=RoutePair)
    blocking_pair.pair_status = "ACTIVE"

    point_result = MagicMock()
    point_result.scalar_one_or_none.return_value = mock_point
    blocking_result = MagicMock()
    blocking_result.scalar_one_or_none.return_value = blocking_pair
    mock_session.execute = AsyncMock(side_effect=[point_result, blocking_result])

    response = app_client.patch(
        f"/api/v1/points/{location_id}",
        json={"is_active": False},
        headers={"If-Match": '"2"'},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "LOCATION_POINT_IN_USE_BY_ACTIVE_PAIR"


def test_create_point_code_conflict(app_client, mock_session) -> None:
    existing = MagicMock(spec=LocationPoint)
    existing.code = "IST"
    first_result = MagicMock()
    first_result.scalar_one_or_none.return_value = existing
    mock_session.execute = AsyncMock(return_value=first_result)

    response = app_client.post(
        "/api/v1/points",
        json={
            "code": "IST",
            "name_tr": "?stanbul",
            "name_en": "Istanbul",
            "latitude_6dp": 41.0,
            "longitude_6dp": 29.0,
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "LOCATION_POINT_CODE_CONFLICT"


def test_create_pair_inactive_origin(app_client, mock_session) -> None:
    inactive_origin = MagicMock(spec=LocationPoint)
    inactive_origin.location_id = str(ULID())
    inactive_origin.is_active = False

    active_destination = MagicMock(spec=LocationPoint)
    active_destination.location_id = str(ULID())
    active_destination.is_active = True

    origin_result = MagicMock()
    origin_result.scalar_one_or_none.return_value = inactive_origin
    destination_result = MagicMock()
    destination_result.scalar_one_or_none.return_value = active_destination
    mock_session.execute = AsyncMock(side_effect=[origin_result, destination_result])

    response = app_client.post("/api/v1/pairs", json={"origin_code": "INACT", "destination_code": "ACT"})
    assert response.status_code == 409
    assert response.json()["code"] == "LOCATION_POINT_INACTIVE_FOR_NEW_PAIR"


def test_create_pair_same_origin_destination(app_client, mock_session) -> None:
    same_id = str(ULID())
    same_point = MagicMock(spec=LocationPoint)
    same_point.location_id = same_id
    same_point.is_active = True

    origin_result = MagicMock()
    origin_result.scalar_one_or_none.return_value = same_point
    destination_result = MagicMock()
    destination_result.scalar_one_or_none.return_value = same_point
    mock_session.execute = AsyncMock(side_effect=[origin_result, destination_result])

    response = app_client.post("/api/v1/pairs", json={"origin_code": "IST", "destination_code": "IST"})
    assert response.status_code == 422
    assert response.json()["code"] == "LOCATION_ROUTE_ORIGIN_EQUALS_DESTINATION"


def test_soft_delete_pair_and_already_deleted(app_client, mock_session) -> None:
    pair_id = str(ULID())
    pair = MagicMock(spec=RoutePair)
    pair.pair_status = "DRAFT"
    pair.row_version = 1

    result = MagicMock()
    result.scalar_one_or_none.return_value = pair
    mock_session.execute = AsyncMock(return_value=result)

    delete_response = app_client.delete(f"/api/v1/pairs/{pair_id}", headers={"If-Match": '"1"'})
    assert delete_response.status_code == 204
    assert pair.pair_status == "SOFT_DELETED"
    assert pair.row_version == 2

    pair.pair_status = "SOFT_DELETED"
    already_deleted = app_client.delete(f"/api/v1/pairs/{pair_id}", headers={"If-Match": '"2"'})
    assert already_deleted.status_code == 409
    assert already_deleted.json()["code"] == "LOCATION_ROUTE_PAIR_ALREADY_SOFT_DELETED"


def test_processing_state_guards(app_client, mock_session) -> None:
    pair_id = str(ULID())

    soft_deleted_pair = MagicMock(spec=RoutePair)
    soft_deleted_pair.pair_status = "SOFT_DELETED"
    mock_session.get = AsyncMock(return_value=soft_deleted_pair)
    response = app_client.post(f"/api/v1/pairs/{pair_id}/calculate", json={})
    assert response.status_code == 409
    assert response.json()["code"] == "LOCATION_ROUTE_PAIR_SOFT_DELETED"

    active_pair = MagicMock(spec=RoutePair)
    active_pair.pair_status = "ACTIVE"
    active_pair.pending_forward_version_no = None
    active_pair.pending_reverse_version_no = None
    active_run = MagicMock(spec=ProcessingRun)
    active_run.run_status = "RUNNING"
    run_result = MagicMock()
    run_result.scalar_one_or_none.return_value = active_run
    mock_session.get = AsyncMock(return_value=active_pair)
    mock_session.execute = AsyncMock(return_value=run_result)

    running_response = app_client.post(f"/api/v1/pairs/{pair_id}/calculate", json={})
    assert running_response.status_code == 409
    assert running_response.json()["code"] == "LOCATION_ROUTE_PAIR_ALREADY_RUNNING"

    draft_pair = MagicMock(spec=RoutePair)
    draft_pair.pair_status = "DRAFT"
    draft_pair.pending_forward_version_no = 2
    draft_pair.pending_reverse_version_no = 2
    no_run = MagicMock()
    no_run.scalar_one_or_none.return_value = None
    mock_session.get = AsyncMock(return_value=draft_pair)
    mock_session.execute = AsyncMock(return_value=no_run)

    pending_response = app_client.post(f"/api/v1/pairs/{pair_id}/calculate", json={})
    assert pending_response.status_code == 409
    assert pending_response.json()["code"] == "LOCATION_ROUTE_PAIR_PENDING_DRAFT_EXISTS"


def test_force_fail_respects_sla(app_client, mock_session) -> None:
    run_id = str(ULID())
    mock_run = MagicMock(spec=ProcessingRun)
    mock_run.run_status = "RUNNING"
    mock_run.started_at_utc = datetime.now(UTC)
    mock_run.created_at_utc = datetime.now(UTC)
    mock_run.processing_run_id = run_id
    mock_run.route_pair_id = str(ULID())
    mock_run.attempt_no = 1
    mock_run.provider_mapbox_status = "PENDING"
    mock_run.provider_ors_status = "PENDING"
    mock_run.completed_at_utc = None
    mock_run.updated_at_utc = datetime.now(UTC)
    mock_pair = MagicMock(spec=RoutePair)
    mock_pair.pair_code = "RP_AAAAAAAAAAAAAAAAAAAAAAAAAA"
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = (mock_run, mock_pair)
    mock_session.execute = AsyncMock(return_value=mock_result)

    response = app_client.post(f"/api/v1/pairs/processing-runs/{run_id}/force-fail", headers=SUPER_ADMIN_HEADERS)
    assert response.status_code == 409
    assert response.json()["code"] == "LOCATION_RUN_NOT_STUCK"

    mock_run.trigger_type = "INITIAL_CALCULATE"
    mock_run.started_at_utc = datetime.now(UTC) - timedelta(minutes=35)
    mock_run.created_at_utc = datetime.now(UTC) - timedelta(minutes=35)
    mock_run.completed_at_utc = None
    mock_run.error_message = None

    async def fake_refresh(_obj):
        mock_run.run_status = "FAILED"

    mock_session.refresh = fake_refresh
    success = app_client.post(f"/api/v1/pairs/processing-runs/{run_id}/force-fail", headers=SUPER_ADMIN_HEADERS)
    assert success.status_code == 200


@pytest.mark.asyncio
async def test_approve_soft_deleted_pair_rejected() -> None:
    pair_id = str(ULID())
    mock_pair = MagicMock()
    mock_pair.pair_status = "SOFT_DELETED"
    mock_pair.pending_forward_version_no = 1
    mock_pair.pending_reverse_version_no = 1

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=mock_pair)
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None

    with patch("location_service.processing.approval.async_session_factory", return_value=mock_session):
        with pytest.raises(ValueError, match="soft-deleted"):
            await approve_route_versions(pair_id)


def test_import_export_routes_removed_from_openapi_and_runtime() -> None:
    app = create_app()
    app.dependency_overrides[user_auth_dependency] = lambda: None
    app.dependency_overrides[trip_service_auth_dependency] = lambda: None
    with TestClient(app, raise_server_exceptions=False) as client:
        openapi = client.get("/openapi.json")
        assert openapi.status_code == 200
        paths = openapi.json()["paths"]
        assert "/v1/import" not in paths
        assert "/v1/export" not in paths

        import_response = client.post("/v1/import")
        export_response = client.get("/v1/export")
        assert import_response.status_code == 404
        assert export_response.status_code == 404


@pytest.mark.asyncio
async def test_trigger_processing_only_enqueues_run(mock_session) -> None:
    pair_id = str(ULID())
    run_id = str(ULID())

    with patch("location_service.processing.pipeline.async_session_factory", return_value=mock_session):
        created_run_id = await trigger_processing(pair_id=pair_id, run_id=run_id)

    assert created_run_id == run_id
    created_run = mock_session.add.call_args.args[0]
    assert isinstance(created_run, ProcessingRun)
    assert created_run.processing_run_id == run_id
    assert created_run.route_pair_id == pair_id
    assert created_run.run_status == "QUEUED"
    mock_session.commit.assert_awaited_once()
