import httpx
import asyncio
import subprocess
import time
import uuid

GATEWAY_URL = "http://localhost:8180"
SUPERADMIN_PAYLOAD = {"username": "superadmin", "password": "change-me-immediately"}


async def get_token():
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{GATEWAY_URL}/auth/v1/login", json=SUPERADMIN_PAYLOAD)
        data = resp.json()
        return data["access_token"]


async def run_driver_resilience_test():
    print("--- DRIVER SERVICE RESILIENCE & CHAOS PROBING ---")
    token = await get_token()
    headers = {"Authorization": f"Bearer {token}", "X-Correlation-ID": str(uuid.uuid4())}

    # 1. Pause Postgres
    print("Pausing Postgres...")
    subprocess.run(["docker", "pause", "lojinext-parity-postgres-1"], check=True)

    print("Attempting Driver Creation with paused DB (expect timeout/failure)...")
    async with httpx.AsyncClient(timeout=5.0) as client:
        payload = {
            "company_driver_code": f"CHAOS-{int(time.time())}",
            "full_name": "Chaos Test Driver",
            "phone": "+905550009988",
            "license_class": "CE",
            "employment_start_date": "2024-01-01",
        }
        try:
            resp = await client.post(f"{GATEWAY_URL}/api/v1/drivers", json=payload, headers=headers)
            print(f"Response with paused DB: {resp.status_code}")
        except Exception as e:
            print(f"Request failed as expected: {type(e).__name__}")

    # 2. Resume Postgres
    print("Resuming Postgres...")
    subprocess.run(["docker", "unpause", "lojinext-parity-postgres-1"], check=True)

    # 3. Wait for recovery and retry
    print("Waiting for service recovery (5s)...")
    await asyncio.sleep(5)

    print("Attempting Driver Creation after recovery...")
    async with httpx.AsyncClient(timeout=10.0) as client:
        payload["company_driver_code"] += "-REC"
        resp = await client.post(f"{GATEWAY_URL}/api/v1/drivers", json=payload, headers=headers)
        if resp.status_code == 201:
            driver_id = resp.json().get("driver_id")
            print(f"Driver created successfully after recovery: {driver_id}")

            # 4. Final verification: Outbox status
            print("Verifying Outbox status in DB...")
            await asyncio.sleep(2)  # Wait for relay
            check_cmd = f"docker exec lojinext-parity-postgres-1 psql -U lojinext -d driver_service -c \"SELECT publish_status FROM driver_outbox WHERE aggregate_id = '{driver_id}'\""
            subprocess.run(check_cmd, shell=True)
        else:
            print(f"Driver creation failed after recovery: {resp.status_code} - {resp.text}")


if __name__ == "__main__":
    asyncio.run(run_driver_resilience_test())
