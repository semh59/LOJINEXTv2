"""Location Service public contract tests for future frontend consumers."""

from __future__ import annotations

from uuid import uuid4

import pytest
from conftest import ADMIN_HEADERS, SUPER_ADMIN_HEADERS
from httpx import AsyncClient


async def _create_point(client: AsyncClient, *, code: str, latitude: float, longitude: float) -> None:
    response = await client.post(
        "/v1/points",
        json={
            "code": code,
            "name_tr": f"{code} TR",
            "name_en": f"{code} EN",
            "latitude_6dp": latitude,
            "longitude_6dp": longitude,
            "is_active": True,
        },
    )
    assert response.status_code == 201


async def _create_pair(client: AsyncClient, *, origin_code: str, destination_code: str) -> dict[str, object]:
    response = await client.post(
        "/v1/pairs",
        json={"origin_code": origin_code, "destination_code": destination_code, "profile_code": "TIR"},
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_public_endpoints_require_bearer_auth(raw_client: AsyncClient) -> None:
    response = await raw_client.get("/v1/points")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "LOCATION_AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_invalid_sort_uses_problem_json(client: AsyncClient) -> None:
    response = await client.get("/v1/pairs?sort=not-a-real-sort")
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "LOCATION_REQUEST_VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_removed_activate_path_returns_exact_404(client: AsyncClient) -> None:
    response = await client.post(f"/v1/pairs/{uuid4()}/activate")
    assert response.status_code == 404
    assert response.json()["code"] == "LOCATION_ENDPOINT_REMOVED"


@pytest.mark.asyncio
async def test_admin_is_forbidden_on_super_admin_operational_endpoints(raw_client: AsyncClient) -> None:
    force_fail = await raw_client.post(f"/v1/processing-runs/{uuid4()}/force-fail", headers=ADMIN_HEADERS)
    bulk_refresh = await raw_client.post("/v1/bulk-refresh/jobs", headers=ADMIN_HEADERS)

    assert force_fail.status_code == 403
    assert force_fail.json()["code"] == "LOCATION_FORBIDDEN"
    assert bulk_refresh.status_code == 403
    assert bulk_refresh.json()["code"] == "LOCATION_FORBIDDEN"


@pytest.mark.asyncio
async def test_super_admin_operational_endpoints_are_reachable(raw_client: AsyncClient) -> None:
    bulk_refresh = await raw_client.post("/v1/bulk-refresh/jobs", headers=SUPER_ADMIN_HEADERS)
    force_fail = await raw_client.post(f"/v1/processing-runs/{uuid4()}/force-fail", headers=SUPER_ADMIN_HEADERS)

    assert bulk_refresh.status_code == 202
    assert bulk_refresh.json()["status"] == "ACCEPTED"
    assert force_fail.status_code == 404
    assert force_fail.json()["code"] == "LOCATION_PROCESSING_RUN_NOT_FOUND"


@pytest.mark.asyncio
async def test_processing_run_canonical_and_compatibility_paths_match(client: AsyncClient) -> None:
    await _create_point(client, code="PROC_O", latitude=60.0, longitude=60.0)
    await _create_point(client, code="PROC_D", latitude=61.0, longitude=61.0)
    pair = await _create_pair(client, origin_code="PROC_O", destination_code="PROC_D")

    created = await client.post(f"/v1/pairs/{pair['pair_id']}/calculate", json={})
    assert created.status_code == 202
    run_id = created.json()["run_id"]

    canonical = await client.get(f"/v1/processing-runs/{run_id}")
    compatibility = await client.get(f"/v1/pairs/processing-runs/{run_id}")
    pair_runs = await client.get(f"/v1/pairs/{pair['pair_id']}/processing-runs")

    assert canonical.status_code == 200
    assert compatibility.status_code == 200
    assert canonical.json() == compatibility.json()
    assert pair_runs.status_code == 200
    assert pair_runs.json()["meta"]["sort"] == "created_at_utc:desc"
    assert pair_runs.json()["data"][0]["run_id"] == run_id
