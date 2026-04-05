import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def run():
    engine = create_async_engine(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/trip_service_test"
    )
    async with engine.connect() as conn:
        print("Non-nullable columns in trip_outbox:")
        res = await conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'trip_outbox' AND is_nullable = 'NO'"
            )
        )
        for r in res.fetchall():
            print(f" - {r[0]}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
