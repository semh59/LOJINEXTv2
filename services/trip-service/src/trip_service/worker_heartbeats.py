"""Process-safe worker heartbeat helpers."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

HEARTBEAT_DIR = Path(tempfile.gettempdir()) / "trip-service-heartbeats"


@dataclass(frozen=True)
class HeartbeatSnapshot:
    """A single worker heartbeat observation."""

    status: str
    recorded_at_utc: datetime | None


def _heartbeat_path(worker_name: str) -> Path:
    """Return the filesystem path used for the given worker heartbeat."""
    return HEARTBEAT_DIR / f"{worker_name}.heartbeat"


def record_worker_heartbeat(worker_name: str, recorded_at_utc: datetime | None = None) -> None:
    """Persist the latest successful loop timestamp for a worker."""
    timestamp = recorded_at_utc or datetime.now(UTC)
    HEARTBEAT_DIR.mkdir(parents=True, exist_ok=True)
    target = _heartbeat_path(worker_name)
    tmp_path = target.with_suffix(".tmp")
    tmp_path.write_text(timestamp.isoformat(), encoding="utf-8")
    os.replace(tmp_path, target)


def read_worker_heartbeat(worker_name: str) -> datetime | None:
    """Read the latest heartbeat timestamp for a worker."""
    path = _heartbeat_path(worker_name)
    if not path.exists():
        return None
    try:
        return datetime.fromisoformat(path.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def get_worker_heartbeat_snapshot(worker_name: str, stale_after_seconds: int) -> HeartbeatSnapshot:
    """Return a normalized heartbeat status for readiness checks."""
    recorded_at = read_worker_heartbeat(worker_name)
    if recorded_at is None:
        return HeartbeatSnapshot(status="unavailable", recorded_at_utc=None)

    stale_after = timedelta(seconds=stale_after_seconds)
    if datetime.now(UTC) - recorded_at > stale_after:
        return HeartbeatSnapshot(status="stale", recorded_at_utc=recorded_at)
    return HeartbeatSnapshot(status="ok", recorded_at_utc=recorded_at)
