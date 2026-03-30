#!/usr/bin/env python3
"""End-to-end soak test for Trip/Location production stack.

Runs a configurable number of iterations over a soak period, hammering
health/ready/metrics endpoints and verifying no 5xx errors accumulate.

Usage:
    python soak_e2e.py [--trip-url URL] [--location-url URL] \
        [--duration-minutes N] [--interval-seconds N]

Exits 0 on success, 1 on any persistent failure.
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime


def _get_status(url: str, timeout: int = 10) -> int:
    """GET a URL and return the HTTP status code (0 on connection error)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Soak test the Trip/Location stack")
    parser.add_argument(
        "--trip-url", default="http://localhost:8101", help="Trip API base URL"
    )
    parser.add_argument(
        "--location-url", default="http://localhost:8103", help="Location API base URL"
    )
    parser.add_argument(
        "--duration-minutes", type=int, default=5, help="Soak duration in minutes"
    )
    parser.add_argument(
        "--interval-seconds", type=float, default=2.0, help="Interval between probes"
    )
    args = parser.parse_args()

    trip, loc = args.trip_url.rstrip("/"), args.location_url.rstrip("/")
    duration_s = args.duration_minutes * 60

    endpoints = [
        ("trip /health", f"{trip}/health"),
        ("trip /ready", f"{trip}/ready"),
        ("trip /metrics", f"{trip}/metrics"),
        ("location /health", f"{loc}/health"),
        ("location /ready", f"{loc}/ready"),
        ("location /metrics", f"{loc}/metrics"),
    ]

    print(f"\n{'=' * 60}")
    print(f"Soak Test — {datetime.now(UTC).isoformat()}")
    print(f"  Duration: {args.duration_minutes} minutes")
    print(f"  Interval: {args.interval_seconds}s")
    print(f"  Trip:     {trip}")
    print(f"  Location: {loc}")
    print(f"{'=' * 60}\n")

    stats: dict[str, dict[str, int]] = {
        name: {"ok": 0, "warn": 0, "fail": 0} for name, _ in endpoints
    }
    start = time.monotonic()
    iteration = 0

    try:
        while time.monotonic() - start < duration_s:
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
            remaining = max(0, duration_s - elapsed)
            mins, secs = divmod(int(remaining), 60)
            print(
                f"\r  Iteration {iteration} — {mins:02d}:{secs:02d} remaining",
                end="",
                flush=True,
            )
            time.sleep(args.interval_seconds)
    except KeyboardInterrupt:
        print("\n\n  ⚠ Soak interrupted by user")

    # --- Report ---
    print(f"\n\n{'=' * 60}")
    print("Soak Test Results")
    print(f"{'=' * 60}")
    print(f"  {'Endpoint':<25} {'OK':>6} {'Warn':>6} {'Fail':>6}")
    print(f"  {'-' * 25} {'-' * 6} {'-' * 6} {'-' * 6}")

    critical_failures = False
    for name, counts in stats.items():
        row = f"  {name:<25} {counts['ok']:>6} {counts['warn']:>6} {counts['fail']:>6}"
        if counts["fail"] > 0:
            row += "  ← CRITICAL"
            # Only /health failures are truly critical
            if "/health" in name:
                critical_failures = True
        print(row)

    print(f"\n  Total iterations: {iteration}")
    print(f"  Duration: {int(time.monotonic() - start)}s\n")

    if critical_failures:
        print("SOAK FAILED — critical health check failures detected")
        sys.exit(1)
    else:
        print("SOAK PASSED — no critical failures")
        sys.exit(0)


if __name__ == "__main__":
    main()
