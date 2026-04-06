#!/usr/bin/env python3
"""Smoke test utility for the five-service production stack."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime


def _request(
    method: str,
    url: str,
    *,
    body: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 10,
) -> tuple[int, str]:
    data = None
    request_headers = {"Accept": "application/json", **(headers or {})}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)


def _expect(
    failures: list[str],
    *,
    label: str,
    method: str,
    url: str,
    expected_statuses: set[int],
    body: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
    body_contains: tuple[str, ...] = (),
) -> tuple[int, str]:
    status, response_body = _request(method, url, body=body, headers=headers)
    ok = status in expected_statuses and all(fragment in response_body for fragment in body_contains)
    icon = "OK" if ok else "FAIL"
    print(f"  [{icon}] {label}: HTTP {status}")
    if not ok:
        print(f"    Expected one of {sorted(expected_statuses)}")
        if body_contains:
            print(f"    Expected body fragments: {body_contains}")
        print(f"    Body preview: {response_body[:300]}")
        failures.append(label)
    return status, response_body


def _parse_json(body: str) -> dict[str, object]:
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("Expected JSON object.")
    return payload


def _expect_ready(
    failures: list[str],
    *,
    label: str,
    url: str,
) -> None:
    status, body = _expect(failures, label=label, method="GET", url=url, expected_statuses={200})
    if status != 200:
        return
    try:
        payload = _parse_json(body)
    except Exception as exc:  # noqa: BLE001
        print(f"    Ready payload was not valid JSON: {exc}")
        failures.append(label)
        return
    if payload.get("status") != "ready":
        print(f"    Expected readiness status=ready, got: {payload!r}")
        failures.append(label)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test the five-service stack")
    parser.add_argument("--identity-url", default=os.getenv("IDENTITY_API_URL", "http://localhost:8105"))
    parser.add_argument("--trip-url", default=os.getenv("TRIP_API_URL", "http://localhost:8101"))
    parser.add_argument("--location-url", default=os.getenv("LOCATION_API_URL", "http://localhost:8103"))
    parser.add_argument("--driver-url", default=os.getenv("DRIVER_API_URL", "http://localhost:8104"))
    parser.add_argument("--fleet-url", default=os.getenv("FLEET_API_URL", "http://localhost:8102"))
    parser.add_argument(
        "--superadmin-username",
        default=os.getenv("IDENTITY_BOOTSTRAP_SUPERADMIN_USERNAME", "superadmin"),
    )
    parser.add_argument(
        "--superadmin-password",
        default=os.getenv("IDENTITY_BOOTSTRAP_SUPERADMIN_PASSWORD", ""),
    )
    args = parser.parse_args()

    if not args.superadmin_password:
        print("IDENTITY_BOOTSTRAP_SUPERADMIN_PASSWORD is required for smoke authentication.", file=sys.stderr)
        sys.exit(2)

    identity = args.identity_url.rstrip("/")
    trip = args.trip_url.rstrip("/")
    location = args.location_url.rstrip("/")
    driver = args.driver_url.rstrip("/")
    fleet = args.fleet_url.rstrip("/")
    failures: list[str] = []

    print(f"\n{'=' * 60}")
    print(f"Smoke Test - {datetime.now(UTC).isoformat()}")
    print(f"  Identity API: {identity}")
    print(f"  Trip API:     {trip}")
    print(f"  Location API: {location}")
    print(f"  Driver API:   {driver}")
    print(f"  Fleet API:    {fleet}")
    print(f"{'=' * 60}\n")

    print("[Baseline]")
    _expect_ready(failures, label="identity ready", url=f"{identity}/ready")
    _expect_ready(failures, label="trip ready", url=f"{trip}/ready")
    _expect_ready(failures, label="location ready", url=f"{location}/ready")
    _expect_ready(failures, label="driver ready", url=f"{driver}/ready")
    _expect_ready(failures, label="fleet ready", url=f"{fleet}/ready")

    print("\n[Identity]")
    login_status, login_body = _expect(
        failures,
        label="identity login",
        method="POST",
        url=f"{identity}/auth/v1/login",
        expected_statuses={200},
        body={"username": args.superadmin_username, "password": args.superadmin_password},
        body_contains=("access_token", "refresh_token"),
    )
    if login_status != 200:
        print("SMOKE FAILED - identity login is required for the remaining checks")
        sys.exit(1)

    user_token = _parse_json(login_body)["access_token"]
    _expect(
        failures,
        label="identity me",
        method="GET",
        url=f"{identity}/auth/v1/me",
        expected_statuses={200},
        headers=_bearer(str(user_token)),
        body_contains=('"role"',),
    )
    _expect(
        failures,
        label="identity jwks",
        method="GET",
        url=f"{identity}/.well-known/jwks.json",
        expected_statuses={200},
        body_contains=('"keys"',),
    )

    def service_token(service_name: str) -> str:
        status, body = _expect(
            failures,
            label=f"service token {service_name}",
            method="POST",
            url=f"{identity}/auth/v1/token/service",
            expected_statuses={200},
            body={
                "client_id": service_name,
                "client_secret": os.getenv(f"{service_name.upper().replace('-', '_')}_SERVICE_CLIENT_SECRET", ""),
                "audience": os.getenv("AUTH_AUDIENCE", "lojinext-platform"),
            },
            body_contains=("access_token",),
        )
        if status != 200:
            raise RuntimeError(f"Unable to mint service token for {service_name}.")
        return str(_parse_json(body)["access_token"])

    trip_token = service_token("trip-service")
    location_token = service_token("location-service")
    fleet_token = service_token("fleet-service")
    driver_token = service_token("driver-service")

    print("\n[Service Contracts]")
    _expect(
        failures,
        label="location service token can read ready",
        method="GET",
        url=f"{location}/ready",
        expected_statuses={200},
        headers=_bearer(location_token),
    )
    _expect(
        failures,
        label="trip->location resolve contract",
        method="POST",
        url=f"{location}/internal/v1/routes/resolve",
        expected_statuses={200, 404, 422},
        headers=_bearer(trip_token),
        body={
            "origin_name": "SMOKE-ORIGIN",
            "destination_name": "SMOKE-DESTINATION",
            "profile_code": "TIR",
            "language_hint": "AUTO",
        },
    )
    _expect(
        failures,
        label="trip->fleet validation contract",
        method="POST",
        url=f"{fleet}/internal/v1/trip-references/validate",
        expected_statuses={200},
        headers=_bearer(trip_token),
        body={"driver_id": "missing-driver", "vehicle_id": None, "trailer_id": None},
        body_contains=('"driver_valid"', '"vehicle_valid"', '"trailer_valid"'),
    )
    _expect(
        failures,
        label="fleet->driver eligibility contract",
        method="POST",
        url=f"{driver}/internal/v1/drivers/eligibility/check",
        expected_statuses={200},
        headers=_bearer(fleet_token),
        body={"driver_ids": ["missing-driver"]},
        body_contains=('"items"',),
    )
    _expect(
        failures,
        label="fleet->trip reference contract",
        method="POST",
        url=f"{trip}/internal/v1/assets/reference-check",
        expected_statuses={200},
        headers=_bearer(fleet_token),
        body={"asset_type": "DRIVER", "asset_id": "missing-driver"},
        body_contains=('"is_referenced"', '"active_trip_count"'),
    )
    _expect(
        failures,
        label="driver->trip reference contract",
        method="POST",
        url=f"{trip}/internal/v1/assets/reference-check",
        expected_statuses={200},
        headers=_bearer(driver_token),
        body={"asset_type": "DRIVER", "asset_id": "missing-driver"},
        body_contains=('"is_referenced"', '"active_trip_count"'),
    )

    print("\n[Metrics]")
    _expect(failures, label="trip metrics", method="GET", url=f"{trip}/metrics", expected_statuses={200})
    _expect(failures, label="location metrics", method="GET", url=f"{location}/metrics", expected_statuses={200})
    _expect(failures, label="driver metrics", method="GET", url=f"{driver}/metrics", expected_statuses={200})

    print(f"\n{'=' * 60}")
    if failures:
        print(f"SMOKE FAILED - {len(failures)} critical check(s) failed:")
        for failure in failures:
            print(f"  - {failure}")
        sys.exit(1)

    print("SMOKE PASSED - real auth and service-contract checks succeeded")
    sys.exit(0)


if __name__ == "__main__":
    main()
