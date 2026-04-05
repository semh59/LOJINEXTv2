import asyncio
import time
import uuid
from datetime import UTC, datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from trip_service.database import async_session_factory
from trip_service.models import TripOutbox
from trip_service.workers.outbox_relay import _relay_batch
from trip_service.broker import MessageBroker, OutboxMessage


class MockBroker(MessageBroker):
    async def publish(self, message: OutboxMessage) -> None:
        await asyncio.sleep(0.01)  # Simulate network latency

    async def close(self) -> None:
        pass

    async def check_health(self) -> None:
        pass


async def setup_bench_data(count: int):
    async with async_session_factory() as session:
        now = datetime.now(UTC)
        for i in range(count):
            session.add(
                TripOutbox(
                    event_id=uuid.uuid4().hex[:26],
                    aggregate_type="TRIP",
                    aggregate_id=f"BENCH-{i}",
                    aggregate_version=1,
                    event_name="trip.created.v1",
                    schema_version=1,
                    payload_json="{}",
                    partition_key=f"PART-{i}",
                    publish_status="READY",
                    attempt_count=0,
                    created_at_utc=now,
                )
            )
        await session.commit()
    print(f"Setup {count} rows for benchmark.")


async def run_benchmark(batch_size: int, total_rows: int):
    broker = MockBroker()
    start_time = time.perf_counter()
    processed = 0

    while processed < total_rows:
        count = await _relay_batch(broker, worker_id="bench-worker", batch_size=batch_size)
        if count == 0:
            break
        processed += count

    end_time = time.perf_counter()
    duration = end_time - start_time
    tps = processed / duration
    print(f"Benchmark Results:")
    print(f"Total Rows: {processed}")
    print(f"Batch Size: {batch_size}")
    print(f"Duration: {duration:.2f}s")
    print(f"Throughput: {tps:.2f} events/sec")


if __name__ == "__main__":
    # Internal benchmark runner
    async def main():
        await setup_bench_data(200)
        await run_benchmark(batch_size=20, total_rows=200)

    asyncio.run(main())
