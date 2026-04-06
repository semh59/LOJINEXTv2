import httpx
import asyncio
import logging
import uuid
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("parity_trace_sim")

IDENTITY_URL = "http://localhost:8180"
TRIP_URL = "http://localhost:8180"


async def run_simulation():
    correlation_id = str(uuid.uuid4())
    headers = {"X-Correlation-ID": correlation_id}

    logger.info(f"Starting simulation with Correlation-ID: {correlation_id}")

    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Login to get token
        logger.info("Authenticating with Identity Service...")
        try:
            login_resp = await client.post(
                f"{IDENTITY_URL}/auth/v1/login",
                json={"username": "superadmin", "password": "change-me-immediately"},
                headers=headers,
            )
            if login_resp.status_code != 200:
                logger.error(f"Login failed: {login_resp.text}")
                return
        except Exception as e:
            logger.error(f"Connection to Identity Service failed: {e}")
            return

        token = login_resp.json()["access_token"]
        auth_headers = {**headers, "Authorization": f"Bearer {token}"}

        # 2. Trigger Trip Creation (Chain: Trip -> Location -> Fleet)
        # Using verified path: /api/v1/trips
        logger.info("Triggering Trip Creation (Chain: Trip -> Location -> Fleet)...")
        trip_payload = {
            "trip_no": f"T-PARITY-{int(time.time())}",
            "route_pair_id": "01HNKX6R6J5S6W66W6W6W6W6W3",
            "driver_id": "01HNKX6R6J5S6W66W6W6W6W6D1",
            "vehicle_id": "01HNKX6R6J5S6W66W6W6W6W6V1",
            "trailer_id": "01HNKX6R6J5S6W66W6W6W6W6T1",
            "trip_start_local": "2024-04-06T10:00:00",
            "trip_timezone": "Europe/Istanbul",
            "tare_weight_kg": 15000,
            "gross_weight_kg": 40000,
            "net_weight_kg": 25000,
            "note": "Parity E2E Tracing Simulation",
        }

        try:
            trip_resp = await client.post(
                f"{TRIP_URL}/api/v1/trips",
                json=trip_payload,
                headers=auth_headers,
            )

            logger.info(f"Trip API Response Code: {trip_resp.status_code}")
            if trip_resp.status_code >= 400:
                logger.error(f"Trip creation failed: {trip_resp.text}")
            else:
                logger.info("SUCCESS: Trip created successfully.")
                logger.info(f"Trip metadata: {trip_resp.json().get('id')}")
        except Exception as e:
            logger.error(f"Connection to Trip Service failed: {e}")


if __name__ == "__main__":
    asyncio.run(run_simulation())
