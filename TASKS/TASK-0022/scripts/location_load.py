import asyncio
import os
import random
import string
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

BASE_URL = os.getenv("BASE_URL", "http://localhost:8103").rstrip("/")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")
SERVICE_TOKEN = os.getenv("SERVICE_TOKEN")

CONCURRENCY = int(os.getenv("CONCURRENCY", "10"))
DURATION_SECONDS = int(os.getenv("DURATION_SECONDS", str(5 * 60)))
RAMP_UP_SECONDS = int(os.getenv("RAMP_UP_SECONDS", "30"))
TIMEOUT_SECONDS = float(os.getenv("TIMEOUT_SECONDS", "15"))

if not ADMIN_TOKEN:
    raise SystemExit("ADMIN_TOKEN env var is required")
if not SERVICE_TOKEN:
    raise SystemExit("SERVICE_TOKEN env var is required")

ADMIN_HEADERS = {
    "Authorization": f"Bearer {ADMIN_TOKEN}",
    "Content-Type": "application/json",
}
SERVICE_HEADERS = {
    "Authorization": f"Bearer {SERVICE_TOKEN}",
    "Content-Type": "application/json",
}


@dataclass
class Metrics:
    total: int = 0
    errors: int = 0
    status_counts: Dict[int, int] = field(default_factory=dict)
    processing_failed: int = 0

    def record(self, status: int) -> None:
        self.total += 1
        self.status_counts[status] = self.status_counts.get(status, 0) + 1
        if status >= 400:
            self.errors += 1

    @property
    def rate_429(self) -> float:
        count_429 = self.status_counts.get(429, 0)
        return count_429 / self.total if self.total else 0.0


def _rand_suffix(length: int = 8) -> str:
    return "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(length))


async def _request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: Dict[str, str],
    metrics: Metrics,
    json: Optional[Dict[str, Any]] = None,
    allow_404: bool = False,
) -> httpx.Response:
    resp = await client.request(method, url, headers=headers, json=json)
    metrics.record(resp.status_code)
    if resp.status_code >= 400 and not (allow_404 and resp.status_code == 404):
        raise RuntimeError(f"{method} {url} failed with {resp.status_code}: {resp.text}")
    return resp


async def _wait_for_run(
    client: httpx.AsyncClient,
    run_id: str,
    headers: Dict[str, str],
    metrics: Metrics,
) -> Dict[str, Any]:
    url = f"{BASE_URL}/v1/pairs/processing-runs/{run_id}"
    for _ in range(60):
        resp = await _request(client, "GET", url, headers, metrics)
        body = resp.json()
        status = body.get("run_status")
        if status == "SUCCEEDED":
            return body
        if status == "FAILED":
            metrics.processing_failed += 1
            raise RuntimeError(f"processing run failed: {body.get('error_message')}")
        await asyncio.sleep(2)
    raise RuntimeError("processing run timed out")


async def _setup_pair(client: httpx.AsyncClient, metrics: Metrics) -> Dict[str, Any]:
    suffix = _rand_suffix()
    origin_code = f"LOAD_ORG_{suffix}"
    destination_code = f"LOAD_DST_{suffix}"

    origin_payload = {
        "code": origin_code,
        "name_tr": f"Load Origin {suffix}",
        "name_en": f"Load Origin {suffix}",
        "latitude_6dp": 41.0082 + random.uniform(-0.01, 0.01),
        "longitude_6dp": 28.9784 + random.uniform(-0.01, 0.01),
        "is_active": True,
    }
    dest_payload = {
        "code": destination_code,
        "name_tr": f"Load Dest {suffix}",
        "name_en": f"Load Dest {suffix}",
        "latitude_6dp": 39.9334 + random.uniform(-0.01, 0.01),
        "longitude_6dp": 32.8597 + random.uniform(-0.01, 0.01),
        "is_active": True,
    }

    await _request(client, "POST", f"{BASE_URL}/v1/points", ADMIN_HEADERS, metrics, origin_payload)
    await _request(client, "POST", f"{BASE_URL}/v1/points", ADMIN_HEADERS, metrics, dest_payload)

    pair_payload = {
        "origin_code": origin_code,
        "destination_code": destination_code,
        "profile_code": "TIR",
    }
    pair_resp = await _request(client, "POST", f"{BASE_URL}/v1/pairs", ADMIN_HEADERS, metrics, pair_payload)
    pair = pair_resp.json()
    return pair


async def _scenario_mix(
    client: httpx.AsyncClient,
    pair_id: str,
    origin_name_tr: str,
    destination_name_tr: str,
    metrics: Metrics,
    use_refresh: bool,
) -> None:
    # Calculate + wait
    endpoint = "refresh" if use_refresh else "calculate"
    try:
        calc_resp = await _request(
            client,
            "POST",
            f"{BASE_URL}/v1/pairs/{pair_id}/{endpoint}",
            ADMIN_HEADERS,
            metrics,
            {},
        )
    except RuntimeError as exc:
        if (not use_refresh) and "LOCATION_ROUTE_PAIR_ALREADY_ACTIVE_USE_REFRESH" in str(exc):
            calc_resp = await _request(
                client,
                "POST",
                f"{BASE_URL}/v1/pairs/{pair_id}/refresh",
                ADMIN_HEADERS,
                metrics,
                {},
            )
        else:
            raise
    run_id = calc_resp.json().get("run_id")
    if run_id:
        await _wait_for_run(client, run_id, ADMIN_HEADERS, metrics)

    # Pair details + approve with ETag
    details_resp = await _request(
        client,
        "GET",
        f"{BASE_URL}/v1/pairs/{pair_id}",
        ADMIN_HEADERS,
        metrics,
    )
    etag = details_resp.headers.get("ETag")
    if etag:
        approve_headers = dict(ADMIN_HEADERS)
        approve_headers["If-Match"] = etag
        await _request(
            client,
            "POST",
            f"{BASE_URL}/v1/pairs/{pair_id}/approve",
            approve_headers,
            metrics,
            {},
        )

    # Refresh details until ACTIVE with forward version
    details = details_resp.json()
    for _ in range(10):
        if details.get("status") == "ACTIVE" and details.get("active_forward_version_no") is not None:
            break
        await asyncio.sleep(1)
        details_resp = await _request(
            client,
            "GET",
            f"{BASE_URL}/v1/pairs/{pair_id}",
            ADMIN_HEADERS,
            metrics,
        )
        details = details_resp.json()

    # Route versions (if route_id/version present)
    route_id = details.get("forward_route_id")
    version_no = details.get("active_forward_version_no")
    if route_id and version_no:
        await _request(
            client,
            "GET",
            f"{BASE_URL}/v1/routes/{route_id}/versions/{version_no}",
            ADMIN_HEADERS,
            metrics,
            allow_404=True,
        )

    # Internal contracts
    await _request(
        client,
        "POST",
        f"{BASE_URL}/internal/v1/routes/resolve",
        SERVICE_HEADERS,
        metrics,
        {
            "origin_name": origin_name_tr,
            "destination_name": destination_name_tr,
            "profile_code": "TIR",
            "language_hint": "AUTO",
        },
    )
    await _request(
        client,
        "GET",
        f"{BASE_URL}/internal/v1/route-pairs/{pair_id}/trip-context",
        SERVICE_HEADERS,
        metrics,
    )


async def worker(worker_id: int, stop_at: float, metrics: Metrics) -> None:
    timeout = httpx.Timeout(TIMEOUT_SECONDS)
    async with httpx.AsyncClient(timeout=timeout) as client:
        pair = await _setup_pair(client, metrics)
        pair_id = pair.get("pair_id") or pair.get("id")
        if not pair_id:
            raise RuntimeError("pair_id missing in pair response")

        origin_name_tr = pair.get("origin_name_tr") or "Load Origin"
        destination_name_tr = pair.get("destination_name_tr") or "Load Dest"

        first_cycle = True
        while time.monotonic() < stop_at:
            await _scenario_mix(
                client,
                pair_id,
                origin_name_tr,
                destination_name_tr,
                metrics,
                use_refresh=not first_cycle,
            )
            first_cycle = False


async def main() -> None:
    start = time.monotonic()
    stop_at = start + DURATION_SECONDS
    metrics = Metrics()

    tasks: List[asyncio.Task] = []
    for i in range(CONCURRENCY):
        delay = (RAMP_UP_SECONDS / max(CONCURRENCY - 1, 1)) * i
        async def _start_worker(idx: int, d: float) -> None:
            await asyncio.sleep(d)
            await worker(idx, stop_at, metrics)
        tasks.append(asyncio.create_task(_start_worker(i, delay)))

    try:
        await asyncio.gather(*tasks)
    except Exception:
        for task in tasks:
            task.cancel()
        raise
    finally:
        elapsed = time.monotonic() - start
        print("Load test completed")
        print(f"Elapsed seconds: {elapsed:.2f}")
        print(f"Total requests: {metrics.total}")
        print(f"Errors: {metrics.errors}")
        print(f"429 rate: {metrics.rate_429:.2%}")
        if metrics.status_counts:
            print("Status counts:")
            for status, count in sorted(metrics.status_counts.items()):
                print(f"  {status}: {count}")

    if metrics.rate_429 > 0.01:
        raise SystemExit(f"429 rate too high: {metrics.rate_429:.2%}")
    if metrics.processing_failed > 0:
        raise SystemExit("Processing runs failed during load test")


if __name__ == "__main__":
    asyncio.run(main())
