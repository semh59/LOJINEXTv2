import httpx
import asyncio
import jwt
import time

# Target configuration from trigger_parity_trace.py
IDENTITY_URL = "http://localhost:8180"
TRIP_URL = "http://localhost:8180"
SUPERADMIN_PAYLOAD = {"username": "superadmin", "password": "change-me-immediately"}

# Load keys if possible, but for DAST we often test with generated "attacker" keys
PRIVATE_KEY_ATTACKER = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA7V... (Attacker Generated)
-----END RSA PRIVATE KEY-----"""  # Shortened for script


async def test_jwt_boundaries():
    async with httpx.AsyncClient(timeout=5.0) as client:
        print("--- JWT SECURITY PROBING ---")

        # 0. Get a valid token for baseline
        resp = await client.post(f"{IDENTITY_URL}/auth/v1/login", json=SUPERADMIN_PAYLOAD)
        valid_token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {valid_token}"}

        # 1. Test Expired Token
        # We can't easily "expire" a server token, but we can wait or mock if we had clock control.
        # Alternatively, we try to use a token known to be old if we had one.
        # For now, we simulate by sending a manually crafted token with different keys.

        # 2. Algorithm Switching Attack
        # Attempt to use HS256 with the RS256 public key (if known) or just random HS256.
        fake_token_hs256 = jwt.encode(
            {"sub": "admin", "exp": int(time.time()) + 3600}, "secret", algorithm="HS256"
        )
        resp = await client.get(
            f"{TRIP_URL}/api/v1/trips", headers={"Authorization": f"Bearer {fake_token_hs256}"}
        )
        print(f"Algorithm Switch (HS256) -> Status: {resp.status_code} (Expected: 401)")

        # 3. Future Token (nbf check)
        # Craft a token with nbf in the future
        # Note: This requires the actual private key to be useful, otherwise it's just a signature failure.
        # But we want to ensure the code *checks* nbf if signed correctly.

        # 4. Audience Mismatch
        # If we can get a service token, test it against a service it's not intended for.

        # 5. Rate Limiting
        print("Probing Rate Limiting...")
        for i in range(15):
            resp = await client.post(f"{IDENTITY_URL}/auth/v1/login", json=SUPERADMIN_PAYLOAD)
            if resp.status_code == 429:
                print(f"Rate Limit Hit at request {i + 1} [SUCCESS]")
                break
        # 6. Audit 404 for information leakage (PII/Stack traces)
        print("Auditing 404 at /api/v1/locations/ for leakage...")
        resp = await client.get(f"{IDENTITY_URL}/api/v1/locations/", headers=headers)
        server_header = resp.headers.get("Server", "Clean")
        x_powered_by = resp.headers.get("X-Powered-By", "Clean")
        print(f"404 Leakage Audit -> Server: {server_header}, X-Powered-By: {x_powered_by}")
        if "uvicorn" in server_header.lower() or "fastapi" in str(resp.text).lower():
            print("WARNING: Technical metadata found in 404 response.")

        print("--- SECURITY PROBING COMPLETE ---")


if __name__ == "__main__":
    asyncio.run(test_jwt_boundaries())
