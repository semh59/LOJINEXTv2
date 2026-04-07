"""External dependency probes and validation clients."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from trip_service.auth import issue_internal_service_token
from trip_service.config import settings
from trip_service.errors import (
    trip_dependency_unavailable,
    trip_invalid_route_pair,
    trip_validation_error,
)
from trip_service.http_clients import get_dependency_client
from trip_service.observability import correlation_id


@dataclass(frozen=True)
class FleetValidationResult:
    """Normalized response from the Fleet validation endpoint."""

    driver_valid: bool
    vehicle_valid: bool | None
    trailer_valid: bool | None


@dataclass(frozen=True)
class LocationRouteResolution:
    """Route resolution response from location-service."""

    route_id: str
    pair_id: str
    resolution: str


@dataclass(frozen=True)
class LocationTripContext:
    """Trip context response from location-service."""

    pair_id: str
    origin_location_id: str
    origin_name: str
    destination_location_id: str
    destination_name: str
    forward_route_id: str
    forward_duration_s: int
    reverse_route_id: str
    reverse_duration_s: int
    profile_code: str
    pair_status: str


def _fleet_validation_url() -> str:
    """Return the Fleet validation endpoint URL."""
    return f"{settings.fleet_service_url}/internal/v1/trip-references/validate"


def _location_resolve_url() -> str:
    """Return the Location resolve endpoint URL."""
    return f"{settings.location_service_url}/internal/v1/routes/resolve"


def _location_trip_context_url(pair_id: str) -> str:
    """Return the Location trip-context endpoint URL."""
    return f"{settings.location_service_url}/internal/v1/route-pairs/{pair_id}/trip-context"


async def _fleet_service_headers() -> dict[str, str]:
    token = await issue_internal_service_token(audience="fleet-service")
    headers = {"Authorization": f"Bearer {token}"}
    if c_id := correlation_id.get():
        headers["X-Correlation-ID"] = c_id
    return headers


async def _location_service_headers() -> dict[str, str]:
    token = await issue_internal_service_token(audience="location-service")
    headers = {"Authorization": f"Bearer {token}"}
    if c_id := correlation_id.get():
        headers["X-Correlation-ID"] = c_id
    return headers


def _problem_code(response: httpx.Response) -> str | None:
    try:
        data = response.json()
    except ValueError:
        return None
    if isinstance(data, dict):
        code = data.get("code")
        if isinstance(code, str) and code:
            return code
    return None


def _location_validation_error(detail: str) -> Exception:
    return trip_validation_error(
        detail,
        errors=[
            {
                "field": "body.origin_name",
                "message": "origin_name and destination_name do not map to a single active route pair.",
            }
        ],
    )


def _compat_errors_for_field(data: dict[str, object], field_name: str) -> list[dict[str, object]]:
    raw_errors = data.get("errors")
    if not isinstance(raw_errors, list):
        return []
    matches: list[dict[str, object]] = []
    for item in raw_errors:
        if not isinstance(item, dict):
            continue
        candidate_field = item.get("field")
        if isinstance(candidate_field, str) and candidate_field == field_name:
            matches.append(item)
    return matches


def _compat_bool(value: object) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _resolve_trip_compat_flag(
    data: dict[str, object],
    *,
    canonical_key: str,
    legacy_keys: tuple[str, ...],
    error_field: str,
    requested: bool,
) -> bool | None:
    if canonical_key in data:
        return _compat_bool(data.get(canonical_key))
    for legacy_key in legacy_keys:
        if legacy_key in data:
            return _compat_bool(data.get(legacy_key))
    if not requested:
        return None
    if _compat_errors_for_field(data, error_field):
        return False
    if data.get("valid") is True:
        return True
    return None


async def validate_trip_references(
    driver_id: str,
    vehicle_id: str | None,
    trailer_id: str | None,
) -> FleetValidationResult:
    """Validate driver/vehicle/trailer references against Fleet Service."""
    payload = {
        "driver_id": driver_id,
        "vehicle_id": vehicle_id,
        "trailer_id": trailer_id,
    }
    try:
        client = await get_dependency_client()
        response = await client.post(_fleet_validation_url(), json=payload, headers=await _fleet_service_headers())
    except httpx.HTTPError as exc:
        raise trip_dependency_unavailable("Fleet Service validation is unavailable.") from exc

    if response.status_code != 200:
        raise trip_dependency_unavailable(
            f"Fleet Service validation returned unexpected status {response.status_code}."
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise trip_dependency_unavailable("Fleet Service validation returned malformed JSON.") from exc
    if not isinstance(data, dict):
        raise trip_dependency_unavailable("Fleet Service validation returned malformed payload.")
    return FleetValidationResult(
        driver_valid=_resolve_trip_compat_flag(
            data,
            canonical_key="driver_valid",
            legacy_keys=("driver_ok",),
            error_field="driver_id",
            requested=True,
        )
        is True,
        vehicle_valid=_resolve_trip_compat_flag(
            data,
            canonical_key="vehicle_valid",
            legacy_keys=("vehicle_exists",),
            error_field="vehicle_id",
            requested=vehicle_id is not None,
        ),
        trailer_valid=_resolve_trip_compat_flag(
            data,
            canonical_key="trailer_valid",
            legacy_keys=(),
            error_field="trailer_id",
            requested=trailer_id is not None,
        ),
    )


async def ensure_trip_references_valid(
    *,
    driver_id: str,
    vehicle_id: str | None,
    trailer_id: str | None,
    field_prefix: str = "body",
) -> None:
    """Raise a validation problem when Fleet reports invalid references."""
    result = await validate_trip_references(driver_id=driver_id, vehicle_id=vehicle_id, trailer_id=trailer_id)
    errors: list[dict[str, str]] = []

    if not result.driver_valid:
        errors.append({"field": f"{field_prefix}.driver_id", "message": "driver_id is invalid."})
    if vehicle_id is not None and result.vehicle_valid is not True:
        errors.append({"field": f"{field_prefix}.vehicle_id", "message": "vehicle_id is invalid."})
    if trailer_id is not None and result.trailer_valid is not True:
        errors.append({"field": f"{field_prefix}.trailer_id", "message": "trailer_id is invalid."})

    if errors:
        raise trip_validation_error("Trip references are invalid.", errors=errors)


async def resolve_route_by_names(
    *,
    origin_name: str,
    destination_name: str,
    profile_code: str = "TIR",
    language_hint: str = "AUTO",
) -> LocationRouteResolution:
    """Resolve a route and pair from normalized origin/destination names."""
    payload = {
        "origin_name": origin_name,
        "destination_name": destination_name,
        "profile_code": profile_code,
        "language_hint": language_hint,
    }
    try:
        client = await get_dependency_client()
        response = await client.post(_location_resolve_url(), json=payload, headers=await _location_service_headers())
    except httpx.HTTPError as exc:
        raise trip_dependency_unavailable("Location Service route resolution is unavailable.") from exc

    problem_code = _problem_code(response)
    if response.status_code == 404 and problem_code == "LOCATION_ROUTE_RESOLUTION_NOT_FOUND":
        raise _location_validation_error("Trip route could not be resolved.")
    if response.status_code == 422 and problem_code == "ROUTE_AMBIGUOUS":
        raise _location_validation_error("Trip route resolution is ambiguous.")
    if response.status_code != 200:
        raise trip_dependency_unavailable(
            f"Location Service route resolution returned unexpected status {response.status_code}."
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise trip_dependency_unavailable("Location Service route resolution returned malformed JSON.") from exc
    if not isinstance(data, dict):
        raise trip_dependency_unavailable("Location Service route resolution returned malformed payload.")
    try:
        route_id = str(data["route_id"])
        pair_id = str(data["pair_id"])
        resolution = str(data["resolution"])
    except (KeyError, TypeError, ValueError) as exc:
        raise trip_dependency_unavailable("Location Service route resolution returned malformed payload.") from exc
    return LocationRouteResolution(
        route_id=route_id,
        pair_id=pair_id,
        resolution=resolution,
    )


async def fetch_trip_context(pair_id: str, *, field_name: str = "body.route_pair_id") -> LocationTripContext:
    """Fetch forward and reverse trip context for a route pair."""
    del field_name
    try:
        client = await get_dependency_client()
        response = await client.get(_location_trip_context_url(pair_id), headers=await _location_service_headers())
    except httpx.HTTPError as exc:
        raise trip_dependency_unavailable("Location Service trip context is unavailable.") from exc

    problem_code = _problem_code(response)
    if (
        response.status_code == 404
        and problem_code == "LOCATION_ROUTE_PAIR_NOT_FOUND"
        or response.status_code == 409
        and problem_code in {"LOCATION_ROUTE_PAIR_NOT_ACTIVE_USE_CALCULATE", "LOCATION_ROUTE_PAIR_SOFT_DELETED"}
    ):
        raise trip_invalid_route_pair(
            f"The provided route pair cannot be used for trip creation: {problem_code}.",
        )
    if response.status_code != 200:
        raise trip_dependency_unavailable(
            f"Location Service trip context returned unexpected status {response.status_code}."
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise trip_dependency_unavailable("Location Service trip context returned malformed JSON.") from exc
    if not isinstance(data, dict):
        raise trip_dependency_unavailable("Location Service trip context returned malformed payload.")
    try:
        pair_id_value = str(data["pair_id"])
        origin_location_id = str(data["origin_location_id"])
        origin_name = str(data["origin_name"])
        destination_location_id = str(data["destination_location_id"])
        destination_name = str(data["destination_name"])
        forward_route_id = str(data["forward_route_id"])
        forward_duration_s = int(data["forward_duration_s"])
        reverse_route_id = str(data["reverse_route_id"])
        reverse_duration_s = int(data["reverse_duration_s"])
        profile_code = str(data["profile_code"])
        pair_status = str(data["pair_status"])
    except (KeyError, TypeError, ValueError) as exc:
        raise trip_dependency_unavailable("Location Service trip context returned malformed payload.") from exc
    return LocationTripContext(
        pair_id=pair_id_value,
        origin_location_id=origin_location_id,
        origin_name=origin_name,
        destination_location_id=destination_location_id,
        destination_name=destination_name,
        forward_route_id=forward_route_id,
        forward_duration_s=forward_duration_s,
        reverse_route_id=reverse_route_id,
        reverse_duration_s=reverse_duration_s,
        profile_code=profile_code,
        pair_status=pair_status,
    )


async def probe_fleet_service() -> bool:
    """Check that Fleet Service accepts the validation contract."""
    payload = {"driver_id": "healthcheck-driver", "vehicle_id": None, "trailer_id": None}
    try:
        client = await get_dependency_client()
        response = await client.post(_fleet_validation_url(), json=payload, headers=await _fleet_service_headers())
    except httpx.HTTPError:
        return False
    return response.status_code == 200


async def probe_location_service() -> bool:
    """Check that Location Service serves both resolve and trip-context contracts."""
    resolve_payload = {
        "origin_name": "healthcheck-origin",
        "destination_name": "healthcheck-destination",
        "profile_code": "TIR",
        "language_hint": "AUTO",
    }
    headers = await _location_service_headers()
    try:
        client = await get_dependency_client()
        resolve_response = await client.post(_location_resolve_url(), json=resolve_payload, headers=headers)
        context_response = await client.get(
            _location_trip_context_url("00000000-0000-0000-0000-000000000000"),
            headers=headers,
        )
    except httpx.HTTPError:
        return False
    return resolve_response.status_code in {200, 404, 422} and context_response.status_code in {200, 404, 409}
