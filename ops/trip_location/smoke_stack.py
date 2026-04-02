#!/usr/bin/env python3
"""Smoke test utility for Trip/Location production stack.

Usage:
    python smoke_stack.py [--trip-url URL] [--location-url URL]

Exits 0 on success, 1 on any failure.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime


def _get(url: str, *, timeout: int = 10) -> tuple[int, str]:
    """GET a URL and return (status_code, body)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return 0, str(e)


def _check(
    label: str, url: str, *, expect_status: int = 200, body_contains: str | None = None
) -> bool:
    """Run a single smoke check and print result."""
    status, body = _get(url)
    ok = status == expect_status
    if body_contains and ok:
        ok = body_contains in body

    icon = "✓" if ok else "✗"
    print(f"  {icon} {label}: HTTP {status} {'(OK)' if ok else '(FAIL)'}")
    if not ok:
        print(f"    Expected status={expect_status}, got {status}")
        if body_contains:
            print(f"    Expected body to contain: {body_contains!r}")
        print(f"    Body preview: {body[:200]}")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test the Trip/Location stack")
    parser.add_argument(
        "--trip-url", default="http://localhost:8101", help="Trip API base URL"
    )
    parser.add_argument(
        "--location-url", default="http://localhost:8103", help="Location API base URL"
    )
    args = parser.parse_args()

    trip, loc = args.trip_url.rstrip("/"), args.location_url.rstrip("/")
    failures: list[str] = []

    print(f"\n{'=' * 60}")
    print(f"Smoke Test — {datetime.now(UTC).isoformat()}")
    print(f"  Trip API:     {trip}")
    print(f"  Location API: {loc}")
    print(f"{'=' * 60}\n")

    # --- Trip Service ---
    print("[Trip Service]")
    if not _check("health", f"{trip}/health"):
        failures.append("trip /health")
    if not _check("ready", f"{trip}/ready"):
        failures.append("trip /ready")
    if not _check("metrics", f"{trip}/metrics", body_contains="trip_created_total"):
        failures.append("trip /metrics")

    # --- Location Service ---
    print("\n[Location Service]")
    if not _check("health", f"{loc}/health"):
        failures.append("location /health")
    if not _check("ready", f"{loc}/ready"):
        failures.append("location /ready")
    if not _check(
        "metrics", f"{loc}/metrics", body_contains="location_processing_runs_total"
    ):
        failures.append("location /metrics")

    # --- Summary ---
    print(f"\n{'=' * 60}")
    if failures:
        print(f"SMOKE FAILED — {len(failures)} critical check(s) failed:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("SMOKE PASSED — all critical checks succeeded")
        sys.exit(0)


if __name__ == "__main__":
    main()
