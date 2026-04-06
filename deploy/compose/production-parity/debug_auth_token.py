import httpx
import jwt
import json

IDENTITY_URL = "http://localhost:8105"


def decode_token(token, jwks):
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    print(f"Token KID: {kid}")

    payload = jwt.decode(token, options={"verify_signature": False})
    print(f"Token Payload: {json.dumps(payload, indent=2)}")


async def debug_auth():
    async with httpx.AsyncClient() as client:
        # Get JWKS
        jwks_resp = await client.get(f"{IDENTITY_URL}/.well-known/jwks.json")
        jwks = jwks_resp.json()
        print(f"JWKS Keys: {[k.get('kid') for k in jwks['keys']]}")

        # Get Token for Trip Service
        token_resp = await client.post(
            f"{IDENTITY_URL}/auth/v1/token/service",
            json={"client_id": "trip-service", "client_secret": "trip-secret-123"},
        )
        if token_resp.status_code != 200:
            print(f"Token request failed: {token_resp.text}")
            return

        token = token_resp.json()["access_token"]
        decode_token(token, jwks)


if __name__ == "__main__":
    import asyncio

    # Note: I need to use the container IP or Re-expose the port for this script
    # For now, I'll run it inside the identity container or just re-expose 8105 temporarily
    asyncio.run(debug_auth())
