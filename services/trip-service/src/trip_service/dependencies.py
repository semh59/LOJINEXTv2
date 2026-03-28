"""External dependency probes and validation clients."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from trip_service.config import settings
from trip_service.errors import trip_dependency_unavailable, trip_validation_error


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
        async with httpx.AsyncClient(timeout=settings.dependency_timeout_seconds) as client:
            response = await client.post(_fleet_validation_url(), json=payload)
    except httpx.HTTPError as exc:
        raise trip_dependency_unavailable("Fleet Service validation is unavailable.") from exc

    if response.status_code != 200:
        raise trip_dependency_unavailable(
            f"Fleet Service validation returned unexpected status {response.status_code}."
        )

    data = response.json()
    return FleetValidationResult(
        driver_valid=bool(data.get("driver_valid")),
        vehicle_valid=data.get("vehicle_valid"),
        trailer_valid=data.get("trailer_valid"),
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
        async with httpx.AsyncClient(timeout=settings.dependency_timeout_seconds) as client:
            response = await client.post(_location_resolve_url(), json=payload)
    except httpx.HTTPError as exc:
        raise trip_dependency_unavailable("Location Service route resolution is unavailable.") from exc

    if response.status_code == 404:
        raise trip_validation_error(
            "Trip route could not be resolved.",
            errors=[
                {
                    "field": "body.origin_name",
                    "message": "origin_name and destination_name do not map to an active pair.",
                }
            ],
        )
    if response.status_code != 200:
        raise trip_dependency_unavailable(
            f"Location Service route resolution returned unexpected status {response.status_code}."
        )

    data = response.json()
    return LocationRouteResolution(
        route_id=str(data["route_id"]),
        pair_id=str(data["pair_id"]),
        resolution=str(data["resolution"]),
    )


async def fetch_trip_context(pair_id: str, *, field_name: str = "body.route_pair_id") -> LocationTripContext:
    """Fetch forward and reverse trip context for a route pair."""
    try:
        async with httpx.AsyncClient(timeout=settings.dependency_timeout_seconds) as client:
            response = await client.get(_location_trip_context_url(pair_id))
    except httpx.HTTPError as exc:
        raise trip_dependency_unavailable("Location Service trip context is unavailable.") from exc

    if response.status_code == 404:
        raise trip_validation_error(
            "Route pair is invalid or inactive.",
            errors=[
                {
                    "field": field_name,
                    "message": "route_pair_id does not map to an active pair with trip context.",
                }
            ],
        )
    if response.status_code != 200:
        raise trip_dependency_unavailable(
            f"Location Service trip context returned unexpected status {response.status_code}."
        )

    data = response.json()
    return LocationTripContext(
        pair_id=str(data["pair_id"]),
        origin_location_id=str(data["origin_location_id"]),
        origin_name=str(data["origin_name"]),
        destination_location_id=str(data["destination_location_id"]),
        destination_name=str(data["destination_name"]),
        forward_route_id=str(data["forward_route_id"]),
        forward_duration_s=int(data["forward_duration_s"]),
        reverse_route_id=str(data["reverse_route_id"]),
        reverse_duration_s=int(data["reverse_duration_s"]),
        profile_code=str(data["profile_code"]),
        pair_status=str(data["pair_status"]),
    )


async def probe_fleet_service() -> bool:
    """Check that Fleet Service accepts the validation contract."""
    payload = {"driver_id": "healthcheck-driver", "vehicle_id": None, "trailer_id": None}
    try:
        async with httpx.AsyncClient(timeout=settings.dependency_timeout_seconds) as client:
            response = await client.post(_fleet_validation_url(), json=payload)
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
    try:
        async with httpx.AsyncClient(timeout=settings.dependency_timeout_seconds) as client:
            resolve_response = await client.post(_location_resolve_url(), json=resolve_payload)
            context_response = await client.get(
                _location_trip_context_url("00000000-0000-0000-0000-000000000000")
            )
    except httpx.HTTPError:
        return False
    return resolve_response.status_code in {200, 404} and context_response.status_code in {200, 404}
