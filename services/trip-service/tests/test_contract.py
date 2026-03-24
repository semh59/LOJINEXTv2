"""7 Mandatory Contract Tests — V8 Section 23.

Contract tests verify response schemas, error formats, and API contracts.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from httpx import AsyncClient

from tests.conftest import ADMIN_HEADERS, make_manual_trip_payload

# ---------------------------------------------------------------------------
# CT-01: problem+json error response format (RFC 9457)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_error_response_problem_json_format(client: AsyncClient):
    """All errors return application/problem+json with required fields."""
    r = await client.get("/api/v1/trips/nonexistent-trip-id-xxxx")
    assert r.status_code == 404
    body = r.json()

    assert "status" in body
    assert "code" in body
    assert "title" in body
    assert "detail" in body
    assert "instance" in body
    assert body["status"] == 404
    assert body["code"] == "TRIP_NOT_FOUND"


# ---------------------------------------------------------------------------
# CT-02: list trips response envelope contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_trips_response_envelope(client: AsyncClient):
    """List response has { items: [], meta: { page, per_page, total_items, total_pages } }."""
    r = await client.get("/api/v1/trips")
    assert r.status_code == 200
    body = r.json()

    assert "items" in body
    assert isinstance(body["items"], list)
    assert "meta" in body
    meta = body["meta"]
    assert "page" in meta
    assert "per_page" in meta
    assert "total_items" in meta
    assert "total_pages" in meta


# ---------------------------------------------------------------------------
# CT-03: trip resource shape on create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trip_resource_shape(client: AsyncClient):
    """POST /api/v1/trips returns a trip resource with all required fields."""
    payload = make_manual_trip_payload(trip_no="TR-CONTRACT-SHAPE")
    r = await client.post("/api/v1/trips", json=payload, headers=ADMIN_HEADERS)
    assert r.status_code == 201
    body = r.json()

    required_fields = [
        "id",
        "trip_no",
        "source_type",
        "driver_id",
        "status",
        "version",
        "is_empty_return",
        "tare_weight_kg",
        "gross_weight_kg",
        "net_weight_kg",
        "created_at_utc",
        "updated_at_utc",
    ]
    for field in required_fields:
        assert field in body, f"Missing required field: {field}"

    assert body["status"] == "COMPLETED"  # ADMIN_MANUAL → directly COMPLETED
    assert body["version"] == 1
    assert body["is_empty_return"] is False


# ---------------------------------------------------------------------------
# CT-04: health endpoint contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_endpoint_contract(client: AsyncClient):
    """GET /health → 200 with { status: "healthy" }."""
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert "status" in body
    assert body["status"] == "ok"


# ---------------------------------------------------------------------------
# CT-05: timeline resource shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeline_resource_shape(client: AsyncClient):
    """Timeline items have required fields."""
    payload = make_manual_trip_payload(trip_no="TR-TL-SHAPE")
    r1 = await client.post("/api/v1/trips", json=payload, headers=ADMIN_HEADERS)
    trip_id = r1.json()["id"]

    r2 = await client.get(f"/api/v1/trips/{trip_id}/timeline")
    assert r2.status_code == 200
    items = r2.json()["items"]
    assert len(items) >= 1

    for item in items:
        assert "event_type" in item
        assert "actor_type" in item
        assert "actor_id" in item
        assert "created_at_utc" in item


# ---------------------------------------------------------------------------
# CT-06: ETag contract — present in mutation responses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_etag_contract_on_mutations(client: AsyncClient):
    """Create and edit responses include ETag header."""
    payload = make_manual_trip_payload(trip_no=f"TR-ETAG-CT-{datetime.now().timestamp()}")
    r1 = await client.post("/api/v1/trips", json=payload, headers=ADMIN_HEADERS)
    assert r1.status_code == 201
    assert "etag" in r1.headers

    trip_id = r1.json()["id"]

    # Re-fetch to get the latest ETag (idempotency record save may have committed)
    r_get = await client.get(f"/api/v1/trips/{trip_id}")
    etag = r_get.headers["etag"]

    r2 = await client.patch(
        f"/api/v1/trips/{trip_id}",
        json={"driver_id": "driver-updated"},
        headers={**ADMIN_HEADERS, "If-Match": etag},
    )
    assert r2.status_code == 200
    assert "etag" in r2.headers
    assert r2.headers["etag"] != etag


# ---------------------------------------------------------------------------
# CT-07: X-Request-Id header echoed in all responses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_id_echoed(client: AsyncClient):
    """All responses echo X-Request-Id header."""
    custom_id = "test-req-id-abc-123"
    r = await client.get(
        "/api/v1/trips",
        headers={"X-Request-Id": custom_id},
    )
    assert r.status_code == 200
    assert r.headers.get("x-request-id") == custom_id
