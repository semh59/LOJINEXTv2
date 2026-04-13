"""Deep dependency-client and contract parsing tests."""

from __future__ import annotations

import httpx
import pytest

import trip_service.dependencies as deps
from trip_service.dependencies import (
    FleetValidationResult,
    ensure_trip_references_valid,
    fetch_trip_context,
    probe_fleet_service,
    probe_location_service,
    resolve_route_by_names,
    validate_trip_references,
)

pytestmark = pytest.mark.unit


class _StubClient:
    def __init__(
        self,
        *,
        post_response: httpx.Response | None = None,
        get_response: httpx.Response | None = None,
        post_exc: Exception | None = None,
        get_exc: Exception | None = None,
    ) -> None:
        self.post_response = post_response
        self.get_response = get_response
        self.post_exc = post_exc
        self.get_exc = get_exc
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    async def post(self, url: str, **kwargs):
        self.calls.append(("POST", url, kwargs))
        if self.post_exc is not None:
            raise self.post_exc
        return self.post_response

    async def get(self, url: str, **kwargs):
        self.calls.append(("GET", url, kwargs))
        if self.get_exc is not None:
            raise self.get_exc
        return self.get_response


def _response(
    method: str,
    url: str,
    status_code: int,
    *,
    json_data=None,
    text_data: str | None = None,
) -> httpx.Response:
    request = httpx.Request(method, url)
    if json_data is not None:
        return httpx.Response(status_code, json=json_data, request=request)
    return httpx.Response(status_code, text=text_data or "", request=request)


def _client_factory(client: _StubClient):
    async def _get_client():
        return client

    return _get_client


@pytest.mark.asyncio
async def test_dependency_url_and_header_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_issue_token(*, audience: str | None = None) -> str:
        return f"{audience}-token"

    monkeypatch.setattr(deps, "issue_internal_service_token", fake_issue_token)

    assert deps._fleet_validation_url().endswith("/internal/v1/trip-references/validate")
    assert deps._location_resolve_url().endswith("/internal/v1/routes/resolve")
    assert deps._location_trip_context_url("pair-001").endswith("/internal/v1/route-pairs/pair-001/trip-context")
    assert await deps._fleet_service_headers() == {"Authorization": "Bearer fleet-service-token"}
    assert await deps._location_service_headers() == {"Authorization": "Bearer location-service-token"}


def test_problem_code_and_compat_helpers_cover_edge_cases() -> None:
    assert deps._problem_code(_response("GET", "http://service/problem", 500, text_data="not-json")) is None
    assert deps._problem_code(_response("GET", "http://service/problem", 400, json_data={"detail": "oops"})) is None
    assert deps._problem_code(_response("GET", "http://service/problem", 400, json_data={"code": "BOOM"})) == "BOOM"
    assert deps._compat_errors_for_field({"errors": "bad"}, "driver_id") == []
    assert deps._compat_errors_for_field(
        {"errors": [None, {"field": "vehicle_id"}, {"field": "driver_id"}]},
        "driver_id",
    ) == [{"field": "driver_id"}]
    assert deps._compat_bool(None) is None
    assert deps._compat_bool(False) is False
    assert deps._compat_bool("yes") is True
    assert (
        deps._resolve_trip_compat_flag(
            {"driver_valid": False},
            canonical_key="driver_valid",
            legacy_keys=("driver_ok",),
            error_field="driver_id",
            requested=True,
        )
        is False
    )
    assert (
        deps._resolve_trip_compat_flag(
            {"driver_ok": 1},
            canonical_key="driver_valid",
            legacy_keys=("driver_ok",),
            error_field="driver_id",
            requested=True,
        )
        is True
    )
    assert (
        deps._resolve_trip_compat_flag(
            {},
            canonical_key="vehicle_valid",
            legacy_keys=("vehicle_exists",),
            error_field="vehicle_id",
            requested=False,
        )
        is None
    )
    assert (
        deps._resolve_trip_compat_flag(
            {"errors": [{"field": "trailer_id"}]},
            canonical_key="trailer_valid",
            legacy_keys=(),
            error_field="trailer_id",
            requested=True,
        )
        is False
    )
    assert (
        deps._resolve_trip_compat_flag(
            {"valid": True},
            canonical_key="vehicle_valid",
            legacy_keys=("vehicle_exists",),
            error_field="vehicle_id",
            requested=True,
        )
        is True
    )
    assert (
        deps._resolve_trip_compat_flag(
            {},
            canonical_key="vehicle_valid",
            legacy_keys=("vehicle_exists",),
            error_field="vehicle_id",
            requested=True,
        )
        is None
    )


@pytest.mark.asyncio
async def test_validate_trip_references_accepts_canonical_and_legacy_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_issue_token(*, audience: str | None = None) -> str:
        assert audience == "fleet-service"
        return "service-token"

    canonical_client = _StubClient(
        post_response=_response(
            "POST",
            "http://fleet/internal/v1/trip-references/validate",
            200,
            json_data={"driver_valid": True, "vehicle_valid": True, "trailer_valid": None},
        )
    )
    monkeypatch.setattr(deps, "issue_internal_service_token", fake_issue_token)
    monkeypatch.setattr(deps, "get_dependency_client", _client_factory(canonical_client))

    canonical = await validate_trip_references("driver-001", "vehicle-001", None)

    assert canonical == FleetValidationResult(driver_valid=True, vehicle_valid=True, trailer_valid=None)
    assert canonical_client.calls[0][2]["headers"] == {"Authorization": "Bearer service-token"}

    legacy_client = _StubClient(
        post_response=_response(
            "POST",
            "http://fleet/internal/v1/trip-references/validate",
            200,
            json_data={"driver_ok": True, "vehicle_exists": False, "errors": [{"field": "trailer_id"}], "valid": True},
        )
    )
    monkeypatch.setattr(deps, "get_dependency_client", _client_factory(legacy_client))

    legacy = await validate_trip_references("driver-001", "vehicle-001", "trailer-001")

    assert legacy == FleetValidationResult(driver_valid=True, vehicle_valid=False, trailer_valid=False)


@pytest.mark.asyncio
async def test_validate_trip_references_rejects_http_and_payload_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_issue_token(*, audience: str | None = None) -> str:
        del audience
        return "service-token"

    monkeypatch.setattr(deps, "issue_internal_service_token", fake_issue_token)

    error_client = _StubClient(post_exc=httpx.ConnectError("down"))
    monkeypatch.setattr(deps, "get_dependency_client", _client_factory(error_client))
    with pytest.raises(Exception) as exc_info:
        await validate_trip_references("driver-001", None, None)
    assert getattr(exc_info.value, "code", None) == "TRIP_DEPENDENCY_UNAVAILABLE"

    malformed_json_client = _StubClient(
        post_response=_response("POST", "http://fleet/internal/v1/trip-references/validate", 200, text_data="not-json")
    )
    monkeypatch.setattr(deps, "get_dependency_client", _client_factory(malformed_json_client))
    with pytest.raises(Exception) as exc_info:
        await validate_trip_references("driver-001", None, None)
    assert getattr(exc_info.value, "code", None) == "TRIP_DEPENDENCY_UNAVAILABLE"

    malformed_shape_client = _StubClient(
        post_response=_response("POST", "http://fleet/internal/v1/trip-references/validate", 200, json_data=["bad"])
    )
    monkeypatch.setattr(deps, "get_dependency_client", _client_factory(malformed_shape_client))
    with pytest.raises(Exception) as exc_info:
        await validate_trip_references("driver-001", None, None)
    assert getattr(exc_info.value, "code", None) == "TRIP_DEPENDENCY_UNAVAILABLE"


@pytest.mark.asyncio
async def test_ensure_trip_references_valid_uses_field_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_validate(*args, **kwargs):
        del args, kwargs
        return FleetValidationResult(driver_valid=False, vehicle_valid=False, trailer_valid=True)

    monkeypatch.setattr(deps, "validate_trip_references", fake_validate)

    with pytest.raises(Exception) as exc_info:
        await ensure_trip_references_valid(
            driver_id="driver-001",
            vehicle_id="vehicle-001",
            trailer_id="trailer-001",
            field_prefix="body.empty_return",
        )

    assert getattr(exc_info.value, "code", None) == "TRIP_VALIDATION_ERROR"
    assert exc_info.value.errors == [
        {"field": "body.empty_return.driver_id", "message": "driver_id is invalid."},
        {"field": "body.empty_return.vehicle_id", "message": "vehicle_id is invalid."},
    ]


@pytest.mark.asyncio
async def test_ensure_trip_references_valid_reports_invalid_trailer(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_validate(*args, **kwargs):
        del args, kwargs
        return FleetValidationResult(driver_valid=True, vehicle_valid=True, trailer_valid=False)

    monkeypatch.setattr(deps, "validate_trip_references", fake_validate)

    with pytest.raises(Exception) as exc_info:
        await ensure_trip_references_valid(
            driver_id="driver-001",
            vehicle_id="vehicle-001",
            trailer_id="trailer-001",
        )

    assert getattr(exc_info.value, "code", None) == "TRIP_VALIDATION_ERROR"
    assert exc_info.value.errors == [{"field": "body.trailer_id", "message": "trailer_id is invalid."}]


@pytest.mark.asyncio
async def test_resolve_route_by_names_maps_contract_and_payload_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_issue_token(*, audience: str | None = None) -> str:
        assert audience == "location-service"
        return "location-token"

    monkeypatch.setattr(deps, "issue_internal_service_token", fake_issue_token)

    not_found_client = _StubClient(
        post_response=_response(
            "POST",
            "http://location/internal/v1/routes/resolve",
            404,
            json_data={"code": "LOCATION_ROUTE_RESOLUTION_NOT_FOUND"},
        )
    )
    monkeypatch.setattr(deps, "get_dependency_client", _client_factory(not_found_client))
    with pytest.raises(Exception) as exc_info:
        await resolve_route_by_names(origin_name="Istanbul", destination_name="Ankara")
    assert getattr(exc_info.value, "code", None) == "TRIP_VALIDATION_ERROR"

    ambiguous_client = _StubClient(
        post_response=_response(
            "POST",
            "http://location/internal/v1/routes/resolve",
            422,
            json_data={"code": "ROUTE_AMBIGUOUS"},
        )
    )
    monkeypatch.setattr(deps, "get_dependency_client", _client_factory(ambiguous_client))
    with pytest.raises(Exception) as exc_info:
        await resolve_route_by_names(origin_name="Istanbul", destination_name="Ankara")
    assert getattr(exc_info.value, "code", None) == "TRIP_VALIDATION_ERROR"

    malformed_client = _StubClient(
        post_response=_response("POST", "http://location/internal/v1/routes/resolve", 200, json_data={"pair_id": "p"})
    )
    monkeypatch.setattr(deps, "get_dependency_client", _client_factory(malformed_client))
    with pytest.raises(Exception) as exc_info:
        await resolve_route_by_names(origin_name="Istanbul", destination_name="Ankara")
    assert getattr(exc_info.value, "code", None) == "TRIP_DEPENDENCY_UNAVAILABLE"


@pytest.mark.asyncio
async def test_resolve_route_by_names_maps_transport_and_unexpected_status_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_issue_token(*, audience: str | None = None) -> str:
        del audience
        return "location-token"

    monkeypatch.setattr(deps, "issue_internal_service_token", fake_issue_token)

    error_client = _StubClient(post_exc=httpx.ConnectError("down"))
    monkeypatch.setattr(deps, "get_dependency_client", _client_factory(error_client))
    with pytest.raises(Exception) as exc_info:
        await resolve_route_by_names(origin_name="Istanbul", destination_name="Ankara")
    assert getattr(exc_info.value, "code", None) == "TRIP_DEPENDENCY_UNAVAILABLE"

    unexpected_client = _StubClient(
        post_response=_response("POST", "http://location/internal/v1/routes/resolve", 503, json_data={})
    )
    monkeypatch.setattr(deps, "get_dependency_client", _client_factory(unexpected_client))
    with pytest.raises(Exception) as exc_info:
        await resolve_route_by_names(origin_name="Istanbul", destination_name="Ankara")
    assert getattr(exc_info.value, "code", None) == "TRIP_DEPENDENCY_UNAVAILABLE"

    malformed_json_client = _StubClient(
        post_response=_response("POST", "http://location/internal/v1/routes/resolve", 200, text_data="bad-json")
    )
    monkeypatch.setattr(deps, "get_dependency_client", _client_factory(malformed_json_client))
    with pytest.raises(Exception) as exc_info:
        await resolve_route_by_names(origin_name="Istanbul", destination_name="Ankara")
    assert getattr(exc_info.value, "code", None) == "TRIP_DEPENDENCY_UNAVAILABLE"


@pytest.mark.asyncio
async def test_fetch_trip_context_maps_business_and_payload_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_issue_token(*, audience: str | None = None) -> str:
        assert audience == "location-service"
        return "location-token"

    monkeypatch.setattr(deps, "issue_internal_service_token", fake_issue_token)

    missing_client = _StubClient(
        get_response=_response(
            "GET",
            "http://location/internal/v1/route-pairs/pair-001/trip-context",
            404,
            json_data={"code": "LOCATION_ROUTE_PAIR_NOT_FOUND"},
        )
    )
    monkeypatch.setattr(deps, "get_dependency_client", _client_factory(missing_client))
    with pytest.raises(Exception) as exc_info:
        await fetch_trip_context("pair-001")
    assert getattr(exc_info.value, "code", None) == "TRIP_INVALID_ROUTE_PAIR"

    inactive_client = _StubClient(
        get_response=_response(
            "GET",
            "http://location/internal/v1/route-pairs/pair-001/trip-context",
            409,
            json_data={"code": "LOCATION_ROUTE_PAIR_SOFT_DELETED"},
        )
    )
    monkeypatch.setattr(deps, "get_dependency_client", _client_factory(inactive_client))
    with pytest.raises(Exception) as exc_info:
        await fetch_trip_context("pair-001")
    assert getattr(exc_info.value, "code", None) == "TRIP_INVALID_ROUTE_PAIR"

    malformed_client = _StubClient(
        get_response=_response(
            "GET",
            "http://location/internal/v1/route-pairs/pair-001/trip-context",
            200,
            json_data={"pair_id": "pair-001"},
        )
    )
    monkeypatch.setattr(deps, "get_dependency_client", _client_factory(malformed_client))
    with pytest.raises(Exception) as exc_info:
        await fetch_trip_context("pair-001")
    assert getattr(exc_info.value, "code", None) == "TRIP_DEPENDENCY_UNAVAILABLE"


@pytest.mark.asyncio
async def test_fetch_trip_context_maps_transport_and_unexpected_status_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_issue_token(*, audience: str | None = None) -> str:
        del audience
        return "location-token"

    monkeypatch.setattr(deps, "issue_internal_service_token", fake_issue_token)

    error_client = _StubClient(get_exc=httpx.ConnectError("down"))
    monkeypatch.setattr(deps, "get_dependency_client", _client_factory(error_client))
    with pytest.raises(Exception) as exc_info:
        await fetch_trip_context("pair-001")
    assert getattr(exc_info.value, "code", None) == "TRIP_DEPENDENCY_UNAVAILABLE"

    unexpected_client = _StubClient(
        get_response=_response(
            "GET",
            "http://location/internal/v1/route-pairs/pair-001/trip-context",
            503,
            json_data={},
        )
    )
    monkeypatch.setattr(deps, "get_dependency_client", _client_factory(unexpected_client))
    with pytest.raises(Exception) as exc_info:
        await fetch_trip_context("pair-001")
    assert getattr(exc_info.value, "code", None) == "TRIP_DEPENDENCY_UNAVAILABLE"

    malformed_json_client = _StubClient(
        get_response=_response(
            "GET",
            "http://location/internal/v1/route-pairs/pair-001/trip-context",
            200,
            text_data="bad",
        )
    )
    monkeypatch.setattr(deps, "get_dependency_client", _client_factory(malformed_json_client))
    with pytest.raises(Exception) as exc_info:
        await fetch_trip_context("pair-001")
    assert getattr(exc_info.value, "code", None) == "TRIP_DEPENDENCY_UNAVAILABLE"


@pytest.mark.asyncio
async def test_probe_fleet_service_returns_false_on_http_error_or_unexpected_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_issue_token(*, audience: str | None = None) -> str:
        del audience
        return "service-token"

    monkeypatch.setattr(deps, "issue_internal_service_token", fake_issue_token)

    error_client = _StubClient(post_exc=httpx.ConnectError("down"))
    monkeypatch.setattr(deps, "get_dependency_client", _client_factory(error_client))
    assert await probe_fleet_service() is False

    bad_status_client = _StubClient(
        post_response=_response("POST", "http://fleet/internal/v1/trip-references/validate", 503, json_data={})
    )
    monkeypatch.setattr(deps, "get_dependency_client", _client_factory(bad_status_client))
    assert await probe_fleet_service() is False


@pytest.mark.asyncio
async def test_probe_fleet_service_returns_true_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_issue_token(*, audience: str | None = None) -> str:
        del audience
        return "service-token"

    monkeypatch.setattr(deps, "issue_internal_service_token", fake_issue_token)
    monkeypatch.setattr(
        deps,
        "get_dependency_client",
        _client_factory(
            _StubClient(
                post_response=_response(
                    "POST",
                    "http://fleet/internal/v1/trip-references/validate",
                    200,
                    json_data={"driver_valid": True},
                )
            )
        ),
    )

    assert await probe_fleet_service() is True


@pytest.mark.asyncio
async def test_probe_location_service_uses_tolerated_status_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_issue_token(*, audience: str | None = None) -> str:
        del audience
        return "service-token"

    monkeypatch.setattr(deps, "issue_internal_service_token", fake_issue_token)

    tolerated_client = _StubClient(
        post_response=_response(
            "POST",
            "http://location/internal/v1/routes/resolve",
            422,
            json_data={"code": "ROUTE_AMBIGUOUS"},
        ),
        get_response=_response(
            "GET",
            "http://location/internal/v1/route-pairs/00000000-0000-0000-0000-000000000000/trip-context",
            409,
            json_data={"code": "LOCATION_ROUTE_PAIR_SOFT_DELETED"},
        ),
    )
    monkeypatch.setattr(deps, "get_dependency_client", _client_factory(tolerated_client))
    assert await probe_location_service() is True

    failing_client = _StubClient(
        post_response=_response("POST", "http://location/internal/v1/routes/resolve", 500, json_data={}),
        get_response=_response(
            "GET",
            "http://location/internal/v1/route-pairs/00000000-0000-0000-0000-000000000000/trip-context",
            200,
            json_data={},
        ),
    )
    monkeypatch.setattr(deps, "get_dependency_client", _client_factory(failing_client))
    assert await probe_location_service() is False


@pytest.mark.asyncio
async def test_probe_location_service_returns_false_on_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_issue_token(*, audience: str | None = None) -> str:
        del audience
        return "service-token"

    monkeypatch.setattr(deps, "issue_internal_service_token", fake_issue_token)
    monkeypatch.setattr(
        deps,
        "get_dependency_client",
        _client_factory(_StubClient(post_exc=httpx.ConnectError("down"))),
    )

    assert await probe_location_service() is False
