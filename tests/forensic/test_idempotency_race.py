import asyncio
import httpx
import uuid
import json
from datetime import UTC, datetime

# Configuration
TRIP_URL = "http://localhost:8001"  # Assume Trip service is on 8001
# We use a real endpoint that supports idempotency
ENDPOINT = f"{TRIP_URL}/internal/v1/trips/slips/ingest"

# Sample valid payload for Telegram Slip Ingest
PAYLOAD = {
    "source_slip_no": "SLIP-FORENSIC-001",
    "source_reference_key": "msg-12345",
    "file_key": "raw/slip.jpg",
    "raw_text_ref": "Sample text",
    "ocr_confidence": 0.95,
    "normalized_truck_plate": "34ABC123",
    "normalized_trailer_plate": "34XYZ789",
    "origin_name": "Istanbul",
    "destination_name": "Ankara",
    "trip_start_local": "2026-04-07T10:00:00",
    "trip_timezone": "Europe/Istanbul",
    "tare_weight_kg": 15000,
    "gross_weight_kg": 40000,
    "net_weight_kg": 25000,
    "driver_id": "DRV001",
}


async def send_request(client, idempotency_key):
    try:
        resp = await client.post(
            ENDPOINT,
            json=PAYLOAD,
            headers={
                "Idempotency-Key": idempotency_key,
                "Authorization": "Bearer service-token",
            },
        )
        return resp
    except Exception as e:
        return str(e)


async def test_idempotency_race():
    print("--- Starting Idempotency Race Forensic Test ---")

    idempotency_key = f"race-{uuid.uuid4()}"
    print(f"Using Idempotency-Key: {idempotency_key}")

    async with httpx.AsyncClient() as client:
        # Send 2 concurrent requests
        print("[1/2] Sending 2 concurrent requests...")
        tasks = [send_request(client, idempotency_key) for _ in range(2)]
        results = await asyncio.gather(*tasks)

        status_codes = [
            r.status_code if isinstance(r, httpx.Response) else str(r) for r in results
        ]
        print(f"Results: {status_codes}")

        # Verification:
        # One should be 201 (Created)
        # The other should be 201 (Replayed) or 409 (Conflict if in-flight)
        # and both should have the SAME body.

        bodies = [
            r.json()
            for r in results
            if isinstance(r, httpx.Response) and r.status_code in (201, 200)
        ]
        if len(bodies) == 2:
            if bodies[0]["id"] == bodies[1]["id"]:
                print(
                    "OK: Both requests resolved to the same resource ID (Idempotency worked)"
                )
            else:
                print(
                    f"FAILED: Different IDs created! {bodies[0]['id']} vs {bodies[1]['id']}"
                )
        else:
            print(
                f"INFO: Only {len(bodies)} successful responses. Check for 409 Conflict (In-flight)."
            )

    print("--- Idempotency Race Test Finished ---")


if __name__ == "__main__":
    asyncio.run(test_idempotency_race())
