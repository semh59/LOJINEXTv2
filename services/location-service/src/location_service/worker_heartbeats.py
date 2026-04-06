"""Async SQLAlchemy worker heartbeat helpers for location-service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from location_service.database import async_session_factory
from location_service.models import WorkerHeartbeat


@dataclass(frozen=True)
class HeartbeatSnapshot:
    """A normalized heartbeat observation used by readiness checks."""

    status: str
    recorded_at_utc: datetime | None


async def record_worker_heartbeat(worker_name: str, recorded_at_utc: datetime | None = None) -> None:
    """Persist the worker's latest loop timestamp atomically in the DB."""
    timestamp = recorded_at_utc or datetime.now(UTC)
    async with async_session_factory() as session:
        stmt = insert(WorkerHeartbeat).values(
            worker_name=worker_name,
            recorded_at_utc=timestamp,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["worker_name"],
            set_={"recorded_at_utc": timestamp},
        )
        await session.execute(stmt)
        await session.commit()


async def read_worker_heartbeat(worker_name: str) -> datetime | None:
    """Read a worker heartbeat if present in the DB."""
    async with async_session_factory() as session:
        stmt = select(WorkerHeartbeat.recorded_at_utc).where(WorkerHeartbeat.worker_name == worker_name)
        result = await session.execute(stmt)
        recorded_at = result.scalar_one_or_none()
        return recorded_at


async def get_worker_heartbeat_snapshot(worker_name: str, stale_after_seconds: int) -> HeartbeatSnapshot:
    """Return the worker's readiness-compatible heartbeat state."""
    recorded_at = await read_worker_heartbeat(worker_name)
    if recorded_at is None:
        return HeartbeatSnapshot(status="unavailable", recorded_at_utc=None)

    if datetime.now(UTC) - recorded_at > timedelta(seconds=stale_after_seconds):
        return HeartbeatSnapshot(status="stale", recorded_at_utc=recorded_at)
    return HeartbeatSnapshot(status="ok", recorded_at_utc=recorded_at)
