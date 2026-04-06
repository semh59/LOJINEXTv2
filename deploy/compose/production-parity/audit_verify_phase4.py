import httpx
import asyncio
import logging
import jwt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("audit_verify_phase4")

IDENTITY_URL = "http://localhost:8105"
LOCATION_URL = "http://localhost:8103"
PLATFORM_AUDIENCE = "lojinext-platform"


async def verify_audience_propagation():
    logger.info("--- TEST 1: Audience Propagation Audit ---")
    async with httpx.AsyncClient() as client:
        # Get Platform Token (default audience)
        resp_plat = await client.post(
            f"{IDENTITY_URL}/auth/v1/token/service",
            json={
                "client_id": "trip-service",
                "client_secret": "trip-secret-123",
                "audience": PLATFORM_AUDIENCE,
            },
        )
        if resp_plat.status_code == 200:
            token = resp_plat.json()["access_token"]
            decoded = jwt.decode(token, options={"verify_signature": False})
            logger.info(f"Platform Token Audience: {decoded.get('aud')}")
            assert decoded.get("aud") == PLATFORM_AUDIENCE
        else:
            logger.error(f"Platform token failed: {resp_plat.text}")
            raise Exception("Platform token failed")

        # Get Service-Specific Token (location-service audience)
        resp_svc = await client.post(
            f"{IDENTITY_URL}/auth/v1/token/service",
            json={
                "client_id": "trip-service",
                "client_secret": "trip-secret-123",
                "audience": "location-service",
            },
        )
        if resp_svc.status_code == 200:
            token = resp_svc.json()["access_token"]
            decoded = jwt.decode(token, options={"verify_signature": False})
            logger.info(f"Service Token Audience: {decoded.get('aud')}")
            # This was failing before the fix (was returning platform audience)
            assert decoded.get("aud") == "location-service"
            logger.info("SUCCESS: Audience propagation fix verified.")
        else:
            logger.error(f"Service token failed: {resp_svc.text}")
            raise Exception("Service token failed")

        # Test Invalid Audience
        resp_inv = await client.post(
            f"{IDENTITY_URL}/auth/v1/token/service",
            json={
                "client_id": "trip-service",
                "client_secret": "trip-secret-123",
                "audience": "malicious-service",
            },
        )
        logger.info(
            f"Invalid Audience Response ({resp_inv.status_code}): {resp_inv.text}"
        )
        assert resp_inv.status_code == 400 or resp_inv.status_code == 422
        logger.info("SUCCESS: Invalid audience rejected.")


async def verify_health_toggle():
    logger.info("\n--- TEST 2: Health Toggle Audit ---")
    async with httpx.AsyncClient() as client:
        # Check current state (should be ready with ignore_provider_health=true)
        resp = await client.get(f"{LOCATION_URL}/ready")
        data = resp.json()
        logger.info(f"Location Ready Status: {data.get('status')}")
        logger.info(f"Checks: {data.get('checks')}")
        assert resp.status_code == 200
        assert data.get("status") == "ready"
        logger.info("SUCCESS: Parity health mode verified.")


if __name__ == "__main__":
    asyncio.run(verify_audience_propagation())
    asyncio.run(verify_health_toggle())
