"""Trip Service contract tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from platform_auth_testing import sign_test_token
from sqlalchemy.exc import DBAPIError

from tests.conftest import (
    ADMIN_HEADERS,
    EXCEL_SERVICE_HEADERS,
    SUPER_ADMIN_HEADERS,
    TELEGRAM_SERVICE_HEADERS,
    TEST_JWKS_BUNDLE,
    make_manual_trip_payload,
)
from trip_service.config import settings
from trip_service.worker_heartbeats import record_worker_heartbeat


def _internal_service_headers(service_name: str) -> dict[str, str]:
    """Build internal service headers for trip-service contract tests."""
    token = sign_test_token(TEST_JWKS_BUNDLE, sub=service_name, role="SERVICE", service=service_name)
    return {"Authorization": f"Bearer {token}"}


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
async def test_service_token_cannot_call_public_mutating_trip_endpoints(client: AsyncClient):
    created = await client.post(
        "/api/v1/trips",
        json=make_manual_trip_payload(trip_no="TR-PUBLIC-MUTATE"),
        headers=ADMIN_HEADERS,
    )
    trip_id = created.json()["id"]
    etag = created.headers["etag"]

    patch_response = await client.patch(
        f"/api/v1/trips/{trip_id}",
        json={"driver_id": "driver-002"},
        headers={**TELEGRAM_SERVICE_HEADERS, "If-Match": etag},
    )
    approve_response = await client.post(
        f"/api/v1/trips/{trip_id}/approve",
        json={"note": "approve"},
        headers={**TELEGRAM_SERVICE_HEADERS, "If-Match": etag},
    )

    assert patch_response.status_code == 403
    assert approve_response.status_code == 403
    assert patch_response.json()["code"] == "TRIP_FORBIDDEN"
    assert approve_response.json()["code"] == "TRIP_FORBIDDEN"


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
async def test_removed_legacy_hard_delete_path_rejects_post_method(client: AsyncClient) -> None:
    response = await client.post("/api/v1/trips/some-trip/hard", headers=SUPER_ADMIN_HEADERS)
    assert response.status_code == 405


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


@pytest.mark.asyncio
async def test_internal_reference_endpoints_reject_unknown_service_tokens(client: AsyncClient):
    response = await client.post(
        "/internal/v1/assets/reference-check",
        json={"asset_type": "DRIVER", "asset_id": "driver-001"},
        headers=_internal_service_headers("rogue-service"),
    )
    assert response.status_code == 403
    assert response.json()["code"] == "TRIP_FORBIDDEN"


@pytest.mark.asyncio
async def test_internal_reference_endpoints_reject_admin_tokens(client: AsyncClient):
    response = await client.post(
        "/internal/v1/assets/reference-check",
        json={"asset_type": "DRIVER", "asset_id": "driver-001"},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 403
    assert response.json()["code"] == "TRIP_FORBIDDEN"


@pytest.mark.asyncio
async def test_admin_tokens_cannot_call_internal_service_mutation_endpoints(client: AsyncClient):
    slip_response = await client.post(
        "/internal/v1/trips/slips/ingest",
        json=make_manual_trip_payload(trip_no="TR-NOT-SLIP"),
        headers=ADMIN_HEADERS,
    )
    export_response = await client.get("/internal/v1/trips/excel/export-feed", headers=ADMIN_HEADERS)

    assert slip_response.status_code == 403
    assert export_response.status_code == 403
    assert slip_response.json()["code"] == "TRIP_FORBIDDEN"
    assert export_response.json()["code"] == "TRIP_FORBIDDEN"


@pytest.mark.asyncio
async def test_internal_asset_reference_endpoints_report_driver_vehicle_and_trailer_usage(client: AsyncClient):
    created = await client.post(
        "/api/v1/trips",
        json=make_manual_trip_payload(trip_no="TR-REF-CHECK", trailer_id="trailer-001"),
        headers=ADMIN_HEADERS,
    )
    assert created.status_code == 201

    driver_response = await client.get(
        "/internal/v1/trips/driver-check/driver-001",
        headers=_internal_service_headers("driver-service"),
    )
    assert driver_response.status_code == 200
    assert driver_response.json() == {
        "driver_id": "driver-001",
        "is_referenced": True,
        "active_trip_count": 1,
    }

    vehicle_response = await client.post(
        "/internal/v1/assets/reference-check",
        json={"asset_type": "VEHICLE", "asset_id": "vehicle-001"},
        headers=_internal_service_headers("fleet-service"),
    )
    assert vehicle_response.status_code == 200
    assert vehicle_response.json() == {
        "asset_type": "VEHICLE",
        "asset_id": "vehicle-001",
        "is_referenced": True,
        "active_trip_count": 1,
    }

    trailer_response = await client.post(
        "/internal/v1/assets/reference-check",
        json={"asset_type": "TRAILER", "asset_id": "trailer-001"},
        headers=_internal_service_headers("fleet-service"),
    )
    assert trailer_response.status_code == 200
    assert trailer_response.json() == {
        "asset_type": "TRAILER",
        "asset_id": "trailer-001",
        "is_referenced": True,
        "active_trip_count": 1,
    }


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_prometheus_payload(client: AsyncClient):
    await client.get("/health")

    response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "trip_created_total" in response.text
    assert "http_request_duration_seconds" in response.text


@pytest.mark.asyncio
async def test_health_endpoints_are_served_at_root_paths(client: AsyncClient) -> None:
    # Ensure fresh heartbeats so /ready returns 200
    await record_worker_heartbeat("enrichment-worker")
    await record_worker_heartbeat("outbox-relay")
    await record_worker_heartbeat("cleanup-worker")

    health_response = await client.get("/health")
    ready_response = await client.get("/ready")
    if ready_response.status_code != 200:
        print(f"DEBUG READY RESPONSE: {ready_response.json()}")
    metrics_response = await client.get("/metrics")
    prefixed_health = await client.get("/v1/health")

    assert health_response.status_code == 200
    assert ready_response.status_code == 200
    assert metrics_response.status_code == 200
    assert prefixed_health.status_code == 404


@pytest.mark.asyncio
async def test_readiness_requires_cleanup_worker_heartbeat(client: AsyncClient):
    stale_at = datetime.now(UTC) - timedelta(seconds=settings.worker_heartbeat_timeout_seconds + 5)
    await record_worker_heartbeat("cleanup-worker", recorded_at_utc=stale_at)

    response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"]["auth_verify"] == "ok"
    assert response.json()["checks"]["auth_outbound"] == "ok"
    assert response.json()["checks"]["cleanup_worker"] == "stale"
    assert response.json()["checks"]["broker"] == "ok"


@pytest.mark.asyncio
async def test_readiness_requires_live_outbound_auth(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    async def cold_outbound() -> str:
        return "fail"

    monkeypatch.setattr("trip_service.routers.health.auth_outbound_status", cold_outbound)

    response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"]["auth_outbound"] == "fail"
    assert response.json()["checks"]["broker"] == "ok"


@pytest.mark.asyncio
async def test_readiness_fails_when_outbound_auth_is_invalid(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    async def broken_outbound() -> str:
        return "fail"

    monkeypatch.setattr("trip_service.routers.health.auth_outbound_status", broken_outbound)

    response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"]["auth_outbound"] == "fail"


@pytest.mark.asyncio
async def test_readiness_fails_when_broker_is_unavailable(client: AsyncClient) -> None:
    class FailingBroker:
        async def check_health(self) -> None:
            raise RuntimeError("broker down")

    client._transport.app.state.broker = FailingBroker()  # type: ignore[attr-defined]

    response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["broker"] == "unavailable"


@pytest.mark.asyncio
async def test_readiness_fails_when_database_probe_errors(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenSession:
        async def __aenter__(self):
            raise DBAPIError("SELECT 1", {}, Exception("relation trip_outbox does not exist"), False)

        async def __aexit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return False

    monkeypatch.setattr("trip_service.routers.health.async_session_factory", lambda: BrokenSession())

    response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["database"] == "unavailable"


@pytest.mark.asyncio
async def test_readiness_fails_when_fleet_probe_is_unavailable(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_probe() -> bool:
        return False

    monkeypatch.setattr("trip_service.routers.health.probe_fleet_service", fail_probe)

    response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["fleet_service"] == "unavailable"


@pytest.mark.asyncio
async def test_readiness_fails_when_location_probe_is_unavailable(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_probe() -> bool:
        return False

    monkeypatch.setattr("trip_service.routers.health.probe_location_service", fail_probe)

    response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["location_service"] == "unavailable"
