from __future__ import annotations

from uuid import uuid4

import pytest
from conftest import ADMIN_HEADERS, FORBIDDEN_SERVICE_HEADERS, FORBIDDEN_USER_HEADERS, SUPER_ADMIN_HEADERS
from httpx import AsyncClient


def _point_payload() -> dict[str, object]:
    return {
        "code": "AUTH_PT_01",
        "name_tr": "Auth Point",
        "name_en": "Auth Point",
        "latitude_6dp": 41.0,
        "longitude_6dp": 29.0,
        "is_active": True,
    }

@pytest.mark.asyncio
async def test_public_endpoints_require_admin_token(raw_client: AsyncClient) -> None:
    response = await raw_client.post("/v1/points", json=_point_payload())
    assert response.status_code == 401
    assert response.json()["code"] == "LOCATION_AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_public_endpoints_reject_wrong_role(raw_client: AsyncClient) -> None:
    response = await raw_client.post("/v1/points", json=_point_payload(), headers=FORBIDDEN_USER_HEADERS)
    assert response.status_code == 403
    assert response.json()["code"] == "LOCATION_FORBIDDEN"


@pytest.mark.asyncio
async def test_internal_endpoints_require_trip_service_token(raw_client: AsyncClient) -> None:
    response = await raw_client.post(
        "/internal/v1/routes/resolve",
        json={"origin_name": "A", "destination_name": "B", "profile_code": "TIR", "language_hint": "AUTO"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "LOCATION_AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_internal_endpoints_reject_wrong_service(raw_client: AsyncClient) -> None:
    response = await raw_client.post(
        "/internal/v1/routes/resolve",
        json={"origin_name": "A", "destination_name": "B", "profile_code": "TIR", "language_hint": "AUTO"},
        headers=FORBIDDEN_SERVICE_HEADERS,
    )
    assert response.status_code == 403
    assert response.json()["code"] == "LOCATION_FORBIDDEN"


@pytest.mark.asyncio
async def test_health_and_ready_stay_open(raw_client: AsyncClient) -> None:
    health = await raw_client.get("/health")
    ready = await raw_client.get("/ready")

    assert health.status_code == 200
    assert ready.status_code == 200


@pytest.mark.asyncio
async def test_admin_cannot_force_fail_processing_runs(raw_client: AsyncClient) -> None:
    response = await raw_client.post(
        f"/v1/processing-runs/{uuid4()}/force-fail",
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 403
    assert response.json()["code"] == "LOCATION_FORBIDDEN"


@pytest.mark.asyncio
async def test_admin_cannot_trigger_bulk_refresh(raw_client: AsyncClient) -> None:
    response = await raw_client.post(
        "/v1/bulk-refresh/jobs",
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 403
    assert response.json()["code"] == "LOCATION_FORBIDDEN"


@pytest.mark.asyncio
async def test_super_admin_can_force_fail_processing_runs(raw_client: AsyncClient) -> None:
    response = await raw_client.post(
        f"/v1/processing-runs/{uuid4()}/force-fail",
        headers=SUPER_ADMIN_HEADERS,
    )
    assert response.status_code == 404
    assert response.json()["code"] == "LOCATION_PROCESSING_RUN_NOT_FOUND"


@pytest.mark.asyncio
async def test_super_admin_can_trigger_bulk_refresh(raw_client: AsyncClient) -> None:
    response = await raw_client.post("/v1/bulk-refresh/jobs", headers=SUPER_ADMIN_HEADERS)
    assert response.status_code == 202
    assert response.json()["status"] == "ACCEPTED"
