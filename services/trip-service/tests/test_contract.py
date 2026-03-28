"""Trip Service contract tests."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import (
    ADMIN_HEADERS,
    EXCEL_SERVICE_HEADERS,
    SUPER_ADMIN_HEADERS,
    TELEGRAM_SERVICE_HEADERS,
    make_manual_trip_payload,
)


@pytest.mark.asyncio
async def test_public_endpoints_require_bearer_auth(client: AsyncClient):
    response = await client.post("/api/v1/trips", json=make_manual_trip_payload(trip_no="TR-NO-AUTH"))
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "TRIP_AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_invalid_bearer_token_returns_401(client: AsyncClient):
    response = await client.get("/api/v1/trips", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401
    assert response.json()["code"] == "TRIP_AUTH_INVALID"


@pytest.mark.asyncio
async def test_legacy_headers_are_not_part_of_prod_contract(client: AsyncClient):
    response = await client.post(
        "/api/v1/trips",
        json=make_manual_trip_payload(trip_no="TR-LEGACY"),
        headers={"X-Actor-Type": "ADMIN", "X-Actor-Id": "legacy-admin"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "TRIP_AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_validation_error_uses_problem_json(client: AsyncClient):
    payload = make_manual_trip_payload(trip_no="TR-BAD-WEIGHT", gross_weight_kg=5000, net_weight_kg=1)
    response = await client.post("/api/v1/trips", json=payload, headers=ADMIN_HEADERS)
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "TRIP_VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_invalid_timezone_returns_problem_json(client: AsyncClient):
    payload = make_manual_trip_payload(trip_no="TR-BAD-TZ", trip_timezone="Bad/Timezone")
    response = await client.post("/api/v1/trips", json=payload, headers=ADMIN_HEADERS)
    assert response.status_code == 422
    assert response.json()["code"] == "TRIP_VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_service_token_cannot_call_public_admin_endpoint(client: AsyncClient):
    response = await client.post(
        "/api/v1/trips",
        json=make_manual_trip_payload(trip_no="TR-SVC"),
        headers=TELEGRAM_SERVICE_HEADERS,
    )
    assert response.status_code == 403
    assert response.json()["code"] == "TRIP_FORBIDDEN"


@pytest.mark.asyncio
async def test_admin_cannot_hard_delete(client: AsyncClient):
    created = await client.post(
        "/api/v1/trips",
        json=make_manual_trip_payload(trip_no="TR-HARD-403"),
        headers=ADMIN_HEADERS,
    )
    cancelled = await client.post(
        f"/api/v1/trips/{created.json()['id']}/cancel",
        headers={**ADMIN_HEADERS, "If-Match": created.headers["etag"]},
    )
    response = await client.post(
        f"/api/v1/trips/{created.json()['id']}/hard-delete",
        json={"reason": "test"},
        headers={**ADMIN_HEADERS, "If-Match": cancelled.headers["etag"]},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "TRIP_FORBIDDEN"


@pytest.mark.asyncio
async def test_hard_delete_requires_reason(client: AsyncClient):
    created = await client.post(
        "/api/v1/trips",
        json=make_manual_trip_payload(trip_no="TR-HARD-REASON"),
        headers=SUPER_ADMIN_HEADERS,
    )
    cancelled = await client.post(
        f"/api/v1/trips/{created.json()['id']}/cancel",
        headers={**SUPER_ADMIN_HEADERS, "If-Match": created.headers["etag"]},
    )
    response = await client.post(
        f"/api/v1/trips/{created.json()['id']}/hard-delete",
        json={},
        headers={**SUPER_ADMIN_HEADERS, "If-Match": cancelled.headers["etag"]},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "TRIP_VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_removed_legacy_hard_delete_path_returns_exact_404(client: AsyncClient):
    response = await client.delete("/api/v1/trips/some-trip/hard", headers=SUPER_ADMIN_HEADERS)
    assert response.status_code == 404
    assert response.json()["code"] == "TRIP_ENDPOINT_REMOVED"


@pytest.mark.asyncio
async def test_driver_statement_range_over_31_days_returns_422(client: AsyncClient):
    response = await client.get(
        "/internal/v1/driver/trips",
        params={"driver_id": "driver-001", "date_from": "2026-01-01", "date_to": "2026-02-02"},
        headers=TELEGRAM_SERVICE_HEADERS,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "TRIP_DATE_RANGE_TOO_LARGE"


@pytest.mark.asyncio
async def test_excel_service_token_is_required_for_export_feed(client: AsyncClient):
    response = await client.get("/internal/v1/trips/excel/export-feed", headers=EXCEL_SERVICE_HEADERS)
    assert response.status_code == 200
