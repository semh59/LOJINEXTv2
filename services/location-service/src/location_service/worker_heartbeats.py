"""Process-safe worker heartbeat helpers for location-service."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

HEARTBEAT_DIR = Path(tempfile.gettempdir()) / "location-service-heartbeats"


@dataclass(frozen=True)
class HeartbeatSnapshot:
    """A normalized heartbeat observation used by readiness checks."""

    status: str
    recorded_at_utc: datetime | None


def _heartbeat_path(worker_name: str) -> Path:
    return HEARTBEAT_DIR / f"{worker_name}.heartbeat"


def record_worker_heartbeat(worker_name: str, recorded_at_utc: datetime | None = None) -> None:
    """Persist the worker's latest loop timestamp atomically."""
    timestamp = recorded_at_utc or datetime.now(UTC)
    HEARTBEAT_DIR.mkdir(parents=True, exist_ok=True)
    target = _heartbeat_path(worker_name)
    tmp_path = target.with_suffix(".tmp")
    tmp_path.write_text(timestamp.isoformat(), encoding="utf-8")
    os.replace(tmp_path, target)


def read_worker_heartbeat(worker_name: str) -> datetime | None:
    """Read a worker heartbeat if present."""
    path = _heartbeat_path(worker_name)
    if not path.exists():
        return None
    try:
        return datetime.fromisoformat(path.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def get_worker_heartbeat_snapshot(worker_name: str, stale_after_seconds: int) -> HeartbeatSnapshot:
    """Return the worker's readiness-compatible heartbeat state."""
    recorded_at = read_worker_heartbeat(worker_name)
    if recorded_at is None:
        return HeartbeatSnapshot(status="unavailable", recorded_at_utc=None)

    if datetime.now(UTC) - recorded_at > timedelta(seconds=stale_after_seconds):
        return HeartbeatSnapshot(status="stale", recorded_at_utc=recorded_at)
    return HeartbeatSnapshot(status="ok", recorded_at_utc=recorded_at)


def clear_worker_heartbeats() -> None:
    """Remove all recorded worker heartbeats. Used by tests."""
    if not HEARTBEAT_DIR.exists():
        return
    for heartbeat_file in HEARTBEAT_DIR.glob("*.heartbeat"):
        heartbeat_file.unlink(missing_ok=True)
