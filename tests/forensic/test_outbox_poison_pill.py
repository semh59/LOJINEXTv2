import asyncio
import uuid
from datetime import UTC, datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Configuration
DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/trip_db"


async def test_outbox_poison_pill():
    print("--- Starting Outbox Poison Pill Forensic Test ---")

    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # 1. Insert a "Poison Pill" (Malformed payload or triggers failure)
        # We'll simulate a failure by inserting a message that the broker will reject
        # (e.g. very large or missing mandatory fields if the broker validates them)
        # For this forensic simulation, we'll just see it hit the retry limit.

        event_id = str(uuid.uuid4())
        print(f"[1/3] Inserting poison pill event {event_id}...")

        await session.execute(
            text("""
                INSERT INTO trip_outbox (
                    outbox_id, event_name, aggregate_type, aggregate_id, 
                    aggregate_version, schema_version, payload_json, 
                    partition_key, publish_status, created_at_utc, next_attempt_at_utc
                ) VALUES (
                    :id, 'POISON_PILL', 'TRIP', 'poison-1', 
                    1, 1, '{"cause_failure": true}', 
                    'poison', 'PENDING', :now, :now
                )
            """),
            {"id": event_id, "now": datetime.now(UTC)},
        )
        await session.commit()

        # 2. Wait for relay to attempt and fail
        print("[2/3] Waiting for relay to process and fail (simulated)...")
        # In a real environment, we'd wait. Here we manually check if it transitioned to FAILED/DEAD_LETTER
        # assuming the relay is running.

        for i in range(5):
            await asyncio.sleep(2)
            result = await session.execute(
                text(
                    "SELECT publish_status, attempt_count, last_error_code FROM trip_outbox WHERE outbox_id = :id"
                ),
                {"id": event_id},
            )
            row = result.fetchone()
            if row:
                print(f"Current status: {row[0]}, Attempts: {row[1]}, Error: {row[2]}")
                if row[0] in ("FAILED", "DEAD_LETTER"):
                    break
            else:
                print("Row not found!")
                break

        # 3. Clean up
        print("[3/3] Cleaning up...")
        await session.execute(
            text("DELETE FROM trip_outbox WHERE outbox_id = :id"), {"id": event_id}
        )
        await session.commit()

    print("--- Outbox Poison Pill Test Finished ---")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(test_outbox_poison_pill())
