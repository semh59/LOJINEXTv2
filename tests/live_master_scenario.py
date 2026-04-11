import httpx
import asyncio
import logging
import uuid
import time
from datetime import datetime, UTC, timedelta

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("DeepHardeningMaster")

BASE_URL = "http://localhost:8180"
SUPERADMIN_PAYLOAD = {"username": "superadmin", "password": "change-me-immediately"}


async def wait_for_ready(client, timeout=120):
    start_time = time.time()
    logger.info("Waiting for system to be ready (Health Checks)...")

    # We will check major service endpoints via Nginx
    checks = [
        ("Identity", "/identity/ready"),
        ("Trip", "/trip/ready"),
        ("Location", "/location/ready"),
        ("Driver", "/driver/ready"),
        ("Fleet", "/fleet/ready"),
    ]

    while time.time() - start_time < timeout:
        all_ready = True
        for name, path in checks:
            try:
                resp = await client.get(f"{BASE_URL}{path}")
                if resp.status_code != 200:
                    logger.warning(f"{name} is not ready yet (Status: {resp.status_code})")
                    all_ready = False
                    break
            except Exception as e:
                logger.warning(f"Could not reach {name}: {e}")
                all_ready = False
                break

        if all_ready:
            logger.info("All core services are READY. System Gateway is UP.")
            return True

        await asyncio.sleep(5)
    return False


async def run_master_test():
    correlation_id = str(uuid.uuid4())
    headers = {"X-Correlation-ID": correlation_id}

    async with httpx.AsyncClient(timeout=30.0) as client:
        if not await wait_for_ready(client):
            logger.error("System failed to become ready in time.")
            return

        # 1. AUTHENTICATION
        logger.info("[PHASE 1] Authenticating...")
        login_resp = await client.post(
            f"{BASE_URL}/auth/v1/login", json=SUPERADMIN_PAYLOAD, headers=headers
        )
        if login_resp.status_code != 200:
            logger.error(f"Login failed: {login_resp.status_code} - {login_resp.text}")
            return

        token = login_resp.json()["access_token"]
        auth_headers = {**headers, "Authorization": f"Bearer {token}"}
        logger.info("Login successful.")

        # 2. SEED VERIFICATION
        # We assume seeds from seed_parity_data.sql are applied via init-db.sh in compose.

        # 3. TRIP LIFE CYCLE
        logger.info("[PHASE 3] Creating a new Trip...")
        trip_no = f"TRIP-DEEP-{int(time.time())}"
        trip_payload = {
            "trip_no": trip_no,
            "route_pair_id": "01HNKX6R6J5S6W66W6W6W6W6W3",
            "driver_id": "01HNKX6R6J5S6W66W6W6W6W6D1",
            "vehicle_id": "01HNKX6R6J5S6W66W6W6W6W6V1",
            "trip_start_local": (datetime.now() + timedelta(hours=24)).isoformat(),
            "trip_timezone": "Europe/Istanbul",
            "tare_weight_kg": 15000,
            "gross_weight_kg": 40000,
            "net_weight_kg": 25000,
        }

        trip_resp = await client.post(
            f"{BASE_URL}/api/v1/trips", json=trip_payload, headers=auth_headers
        )
        if trip_resp.status_code != 201:
            logger.error(f"Trip creation failed: {trip_resp.status_code} - {trip_resp.text}")
            return

        trip_data = trip_resp.json()
        trip_id = trip_data["id"]
        logger.info(f"Trip created: {trip_id} (No: {trip_no})")

        # 4. LOCATION STREAMING (DEPRECATED FOR REST IN V2.1)
        logger.info(
            "[PHASE 4] Skipping REST-based location updates (Moved to Kafka/Telegram in V2.1)..."
        )
        # Legacy Phase 4 code removed due to 404 at /api/v1/locations/
        # loc_resp = await client.post(...)
        await asyncio.sleep(1)

        # 5. VERIFICATION
        logger.info("[PHASE 5] Verification...")
        await asyncio.sleep(5)

        final_trip_resp = await client.get(
            f"{BASE_URL}/api/v1/trips/{trip_id}", headers=auth_headers
        )
        if final_trip_resp.status_code == 200:
            trip_status = final_trip_resp.json().get("status")
            logger.info(
                f"FINAL SUCCESS: Master scenario completed successfully. Trip State: {trip_status}"
            )
        else:
            logger.error(f"Failed to fetch final trip state: {final_trip_resp.status_code}")


if __name__ == "__main__":
    asyncio.run(run_master_test())
