"""Async worker heartbeat helpers for fleet-service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from fleet_service.database import async_session_factory
from fleet_service.models import FleetWorkerHeartbeat
from fleet_service.timestamps import to_utc_aware, utc_now_aware


@dataclass(frozen=True)
class HeartbeatSnapshot:
    """A single worker heartbeat observation."""

    status: str  # "ok" | "stale" | "unavailable"
    recorded_at_utc: datetime | None

async def record_worker_heartbeat(worker_name: str, recorded_at_utc: datetime | None = None) -> None:
    """Persist the latest successful loop timestamp for a worker in the DB."""
    timestamp = to_utc_aware(recorded_at_utc or datetime.now(UTC))
    async with async_session_factory() as session:
        stmt = insert(FleetWorkerHeartbeat).values(
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
    """Read the latest heartbeat timestamp for a worker from the DB."""
    async with async_session_factory() as session:
        stmt = select(FleetWorkerHeartbeat.recorded_at_utc).where(FleetWorkerHeartbeat.worker_name == worker_name)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def get_worker_heartbeat_snapshot(worker_name: str, stale_after_seconds: int) -> HeartbeatSnapshot:
    """Return a normalized heartbeat status for readiness checks."""
    recorded_at = await read_worker_heartbeat(worker_name)
    if recorded_at is None:
        return HeartbeatSnapshot(status="unavailable", recorded_at_utc=None)

    normalized_recorded_at = to_utc_aware(recorded_at)
    stale_after = timedelta(seconds=stale_after_seconds)
    if utc_now_aware().replace(tzinfo=UTC) - normalized_recorded_at > stale_after:
        return HeartbeatSnapshot(status="stale", recorded_at_utc=normalized_recorded_at)
    return HeartbeatSnapshot(status="ok", recorded_at_utc=normalized_recorded_at)
