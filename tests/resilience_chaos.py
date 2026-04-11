import httpx
import asyncio
import subprocess
import time
import uuid
from datetime import datetime, timedelta

TRIP_URL = "http://localhost:8180"
IDENTITY_URL = "http://localhost:8180"
SUPERADMIN_PAYLOAD = {"username": "superadmin", "password": "change-me-immediately"}


async def get_token():
    async with httpx.AsyncClient() as client:
        for attempt in range(5):
            resp = await client.post(f"{IDENTITY_URL}/auth/v1/login", json=SUPERADMIN_PAYLOAD)
            if resp.status_code == 429:
                print(f"Rate limited (429), waiting 5s before retry {attempt + 1}...")
                await asyncio.sleep(5)
                continue

            try:
                data = resp.json()
            except Exception:
                print(f"Login failed (Non-JSON): {resp.status_code} - {resp.text}")
                raise KeyError("access_token")

            if "access_token" not in data:
                print(f"Login failed: {resp.status_code} - {resp.text}")
                raise KeyError("access_token")
            return data["access_token"]
        raise Exception("Authentication failed after multiple retries due to rate limiting.")


async def run_resilience_test():
    print("--- RESILIENCE & CHAOS PROBING ---")
    token = await get_token()
    headers = {"Authorization": f"Bearer {token}", "X-Correlation-ID": str(uuid.uuid4())}

    # 1. Start a trip creation
    # 2. Midway, pause the DB
    print("Interrupting Database during transaction...")
    # Simulation: Start request, then pause container
    # Note: Since we are local, we can use subprocess to call docker

    async with httpx.AsyncClient(timeout=30.0) as client:
        # We'll trigger a background task or just wait
        payload = {
            "trip_no": f"CHAOS-{int(time.time())}",
            "route_pair_id": "01HNKX6R6J5S6W66W6W6W6W6W3",
            "driver_id": "01HNKX6R6J5S6W66W6W6W6W6D1",
            "vehicle_id": "01HNKX6R6J5S6W66W6W6W6W6V1",
            "trip_start_local": (datetime.now() + timedelta(hours=48)).isoformat(),
            "trip_timezone": "Europe/Istanbul",
            "tare_weight_kg": 15000,
            "gross_weight_kg": 40000,
            "net_weight_kg": 25000,
        }

        # Pause Postgres
        subprocess.run(["docker", "pause", "lojinext-parity-postgres-1"], check=True)
        print("Postgres PAUSED.")

        try:
            resp = await client.post(f"{TRIP_URL}/api/v1/trips", json=payload, headers=headers)
            print(f"Response with paused DB: {resp.status_code} (Expected: 500 or timeout)")
        except Exception as e:
            print(f"Request failed as expected: {e}")

        # Resume and check recovery
        subprocess.run(["docker", "unpause", "lojinext-parity-postgres-1"], check=True)
        print("Postgres RESUMED.")

        # Verify if the outbox relay (which should have retried with backoff) eventually succeeds
        # (This requires checking the DB state after some time)
        print("Waiting for Outbox Relay recovery...")
        await asyncio.sleep(10)

        # Check if trip exists
        resp = await client.get(f"{TRIP_URL}/api/v1/trips", headers=headers)
        print(f"Post-recovery check: {resp.status_code}")


if __name__ == "__main__":
    asyncio.run(run_resilience_test())
