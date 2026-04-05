#!/usr/bin/env python3
"""End-to-end soak test for the five-service production stack."""

from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime


def _get_status(url: str, timeout: int = 10) -> int:
    """GET a URL and return the HTTP status code."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception:  # noqa: BLE001
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Soak test the five-service stack")
    parser.add_argument("--identity-url", default=os.getenv("IDENTITY_API_URL", "http://localhost:8105"), help="Identity API base URL")
    parser.add_argument("--trip-url", default=os.getenv("TRIP_API_URL", "http://localhost:8101"), help="Trip API base URL")
    parser.add_argument("--location-url", default=os.getenv("LOCATION_API_URL", "http://localhost:8103"), help="Location API base URL")
    parser.add_argument("--driver-url", default=os.getenv("DRIVER_API_URL", "http://localhost:8104"), help="Driver API base URL")
    parser.add_argument("--fleet-url", default=os.getenv("FLEET_API_URL", "http://localhost:8102"), help="Fleet API base URL")
    parser.add_argument("--duration-minutes", type=int, default=5, help="Soak duration in minutes")
    parser.add_argument("--interval-seconds", type=float, default=2.0, help="Interval between probes")
    args = parser.parse_args()

    identity = args.identity_url.rstrip("/")
    trip = args.trip_url.rstrip("/")
    location = args.location_url.rstrip("/")
    driver = args.driver_url.rstrip("/")
    fleet = args.fleet_url.rstrip("/")
    duration_seconds = args.duration_minutes * 60

    endpoints = [
        ("identity /health", f"{identity}/health"),
        ("identity /ready", f"{identity}/ready"),
        ("identity /.well-known/jwks.json", f"{identity}/.well-known/jwks.json"),
        ("trip /health", f"{trip}/health"),
        ("trip /ready", f"{trip}/ready"),
        ("trip /metrics", f"{trip}/metrics"),
        ("location /health", f"{location}/health"),
        ("location /ready", f"{location}/ready"),
        ("location /metrics", f"{location}/metrics"),
        ("driver /health", f"{driver}/health"),
        ("driver /ready", f"{driver}/ready"),
        ("driver /metrics", f"{driver}/metrics"),
        ("fleet /health", f"{fleet}/health"),
        ("fleet /ready", f"{fleet}/ready"),
        ("fleet /metrics", f"{fleet}/metrics"),
    ]

    print(f"\n{'=' * 60}")
    print(f"Soak Test - {datetime.now(UTC).isoformat()}")
    print(f"  Duration: {args.duration_minutes} minutes")
    print(f"  Interval: {args.interval_seconds}s")
    print(f"  Identity: {identity}")
    print(f"  Trip:     {trip}")
    print(f"  Location: {location}")
    print(f"  Driver:   {driver}")
    print(f"  Fleet:    {fleet}")
    print(f"{'=' * 60}\n")

    stats: dict[str, dict[str, int]] = {name: {"ok": 0, "warn": 0, "fail": 0} for name, _ in endpoints}
    start = time.monotonic()
    iteration = 0

    try:
        while time.monotonic() - start < duration_seconds:
            iteration += 1
            for name, url in endpoints:
                status = _get_status(url)
                if 200 <= status < 300:
                    stats[name]["ok"] += 1
                elif status == 503:
                    stats[name]["warn"] += 1
                else:
                    stats[name]["fail"] += 1

            elapsed = time.monotonic() - start
            remaining = max(0, duration_seconds - elapsed)
            mins, secs = divmod(int(remaining), 60)
            print(f"\r  Iteration {iteration} - {mins:02d}:{secs:02d} remaining", end="", flush=True)
            time.sleep(args.interval_seconds)
    except KeyboardInterrupt:
        print("\n\n  Soak interrupted by user")

    print(f"\n\n{'=' * 60}")
    print("Soak Test Results")
    print(f"{'=' * 60}")
    print(f"  {'Endpoint':<30} {'OK':>6} {'Warn':>6} {'Fail':>6}")
    print(f"  {'-' * 30} {'-' * 6} {'-' * 6} {'-' * 6}")

    critical_failures = False
    for name, counts in stats.items():
        row = f"  {name:<30} {counts['ok']:>6} {counts['warn']:>6} {counts['fail']:>6}"
        if counts["fail"] > 0:
            row += "  <- CRITICAL"
            if "/health" in name or "/ready" in name or "jwks" in name:
                critical_failures = True
        print(row)

    print(f"\n  Total iterations: {iteration}")
    print(f"  Duration: {int(time.monotonic() - start)}s\n")

    if critical_failures:
        print("SOAK FAILED - critical service failures detected")
        sys.exit(1)

    print("SOAK PASSED - no critical failures")
    sys.exit(0)


if __name__ == "__main__":
    main()
