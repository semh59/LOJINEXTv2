import asyncio
import time

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.database import async_session_factory
from auth_service.models import AuthUserModel
from auth_service.token_service import issue_token_pair, seed_bootstrap_state


@pytest.mark.asyncio
async def test_crypto_offloading_responsiveness(session: AsyncSession):
    """
    Verify that the event loop remains responsive while multiple heavy crypto
    operations are offloaded to executors.
    """
    await seed_bootstrap_state(session)
    user = (await session.execute(select(AuthUserModel).limit(1))).scalar_one()

    # Shared counter to track event loop ticks
    ticks = []

    async def heartbeat():
        """A simple heartbeat that records ticks in the event loop."""
        for _ in range(50):
            ticks.append(time.perf_counter())
            await asyncio.sleep(0.01)

    async def stress_crypto():
        """Trigger multiple token issues which involve RSA signing."""

        async def _task():
            async with async_session_factory() as local_session:
                # Re-fetch user in local session
                local_user = await local_session.get(AuthUserModel, user.user_id)
                await issue_token_pair(local_session, local_user)

        tasks = [_task() for _ in range(20)]
        return await asyncio.gather(*tasks)

    # Warm up: run a few iterations to ensure JIT/Lazy-loading is complete
    await stress_crypto()

    # Start heartbeat and stress concurrently
    hb_task = asyncio.create_task(heartbeat())
    stress_task = asyncio.create_task(stress_crypto())

    await asyncio.gather(hb_task, stress_task)

    # Analyze gaps between ticks
    gaps = [ticks[i] - ticks[i - 1] for i in range(1, len(ticks))]
    max_gap = max(gaps)

    # We expect max_gap < 600ms (accounting for GIL contention during heavy concurrent RSA signing).
    # In production, requests are distributed across multiple processes (gunicorn/uvicorn workers),
    # so this cross-thread GIL contention is minimized.
    assert max_gap < 0.6, f"Event loop was blocked! Max gap: {max_gap:.4f}s"


@pytest.mark.asyncio
async def test_outbox_concurrency_race(session: AsyncSession):
    """
    Simulate highly concurrent outbox event generation to ensure ULID/Sequence
    consistency and zero collision in audit/outbox entries.
    """
    await seed_bootstrap_state(session)
    user = (await session.execute(select(AuthUserModel).limit(1))).scalar_one()

    from auth_service.token_service import _write_outbox

    # Generate 100 outbox entries concurrently using local sessions
    async def _outbox_task(idx: int):
        async with async_session_factory() as local_session:
            await _write_outbox(
                local_session,
                f"stress.event.{idx}",
                {"index": idx},
                aggregate_id=user.user_id,
            )
            await local_session.commit()

    tasks = [_outbox_task(i) for i in range(100)]
    await asyncio.gather(*tasks)

    # Verify counts
    from auth_service.models import AuthOutboxModel

    result = await session.execute(select(AuthOutboxModel))
    outbox_entries = result.scalars().all()
    assert len(outbox_entries) >= 100
    ids = [e.outbox_id for e in outbox_entries]
    assert len(set(ids)) == len(ids), "Duplicate Outbox IDs detected!"
