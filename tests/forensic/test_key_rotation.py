import asyncio
import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Configuration
IDENTITY_URL = "http://localhost:8000"
DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/identity_db"


async def test_key_rotation():
    print("--- Starting Auth Key Rotation Forensic Test ---")

    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with httpx.AsyncClient() as client:
        # 1. Login to get an initial token
        print("[1/4] Obtaining initial token...")
        # (Assuming bootstrap admin exists)
        login_resp = await client.post(
            f"{IDENTITY_URL}/auth/token",
            data={
                "username": "admin",
                "password": "admin_password",
                "grant_type": "password",
            },
        )
        if login_resp.status_code != 200:
            print(f"FAILED: Login failed: {login_resp.text}")
            return

        token1 = login_resp.json()["access_token"]
        print("OK: Obtained token 1")

        # 2. Trigger Key Rotation (Simulate via DB since there's no public rotation endpoint yet)
        print("[2/4] Simulating key rotation in database...")
        async with async_session() as session:
            # We'll just wait for the service to auto-generate a new one if we deactivate all?
            # Or manually insert one. Let's manually trigger the 'ensure_active_signing_key' logic
            # by calling an endpoint that uses it after we de-activate current ones.
            await session.execute(
                text("UPDATE identity_signing_keys SET is_active = False")
            )
            await session.commit()

        # Now call login again, it should generate a NEW key
        print("OK: Deactivated old keys. Requesting new token to trigger rotation...")
        login_resp2 = await client.post(
            f"{IDENTITY_URL}/auth/token",
            data={
                "username": "admin",
                "password": "admin_password",
                "grant_type": "password",
            },
        )
        token2 = login_resp2.json()["access_token"]
        print("OK: Obtained token 2 (New Key)")

        # 3. Verify Token 1 still works (Forensic overlap check)
        print("[3/4] Verifying token 1 (Old Key) still works for auth...")
        me_resp1 = await client.get(
            f"{IDENTITY_URL}/auth/me", headers={"Authorization": f"Bearer {token1}"}
        )
        if me_resp1.status_code == 200:
            print("OK: Token 1 still valid (KID-based fallback works)")
        else:
            print(f"FAILED: Token 1 rejected after rotation: {me_resp1.status_code}")

        # 4. Verify Token 2 works
        print("[4/4] Verifying token 2 (New Key) works...")
        me_resp2 = await client.get(
            f"{IDENTITY_URL}/auth/me", headers={"Authorization": f"Bearer {token2}"}
        )
        if me_resp2.status_code == 200:
            print("OK: Token 2 valid")
        else:
            print(f"FAILED: Token 2 rejected: {me_resp2.status_code}")

    print("--- Auth Key Rotation Test Finished ---")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(test_key_rotation())
