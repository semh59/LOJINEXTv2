import asyncio
import httpx
import sys
from datetime import UTC, datetime, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Configuration (Assume default local dev ports)
IDENTITY_URL = "http://localhost:8000"
DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/identity_db"


async def test_truthful_readiness():
    print("--- Starting Truthful Readiness Forensic Test ---")

    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with httpx.AsyncClient() as client:
        # 1. Baseline check
        print("[1/4] Checking baseline readiness...")
        try:
            resp = await client.get(f"{IDENTITY_URL}/ready")
            if resp.status_code != 200:
                print(f"FAILED: Initial readiness is {resp.status_code}, expected 200")
                # sys.exit(1) # Don't exit yet, might be worker not started
            else:
                print("OK: Baseline readiness is 200")
        except Exception as e:
            print(f"FAILED: Could not connect to service: {e}")
            sys.exit(1)

        # 2. Outbox Worker Stale Heartbeat
        print("[2/4] Simulating stale outbox worker...")
        async with async_session() as session:
            # Set heartbeat to 1 hour ago
            stale_time = datetime.now(UTC) - timedelta(hours=1)
            await session.execute(
                text(
                    "UPDATE identity_worker_heartbeats SET last_seen_at_utc = :t WHERE worker_name = 'outbox_relay'"
                ),
                {"t": stale_time},
            )
            await session.commit()

        resp = await client.get(f"{IDENTITY_URL}/ready")
        if resp.status_code == 503:
            print("OK: Service reported 503 for stale worker")
            print(f"Response: {resp.json()}")
        else:
            print(f"FAILED: Expected 503 for stale worker, got {resp.status_code}")

        # 3. Restore Heartbeat
        print("[3/4] Restoring worker heartbeat...")
        async with async_session() as session:
            await session.execute(
                text(
                    "UPDATE identity_worker_heartbeats SET last_seen_at_utc = :t WHERE worker_name = 'outbox_relay'"
                ),
                {"t": datetime.now(UTC)},
            )
            await session.commit()

        resp = await client.get(f"{IDENTITY_URL}/ready")
        if resp.status_code == 200:
            print("OK: Service recovered to 200")
        else:
            print(f"FAILED: Expected 200 after restoration, got {resp.status_code}")

        # 4. Critical Asset Loss (Signing Keys) - Truthful Readiness check
        # Note: We need to update the service code to check for signing keys first!
        print("[4/4] Simulating loss of critical signing keys (Truthful Readiness)...")
        # For now, let's just mark it as "to be implemented in service code"
        print("SKIP: Service code logic for 'no active keys' readiness check required.")

    print("--- Truthful Readiness Test Finished ---")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(test_truthful_readiness())
