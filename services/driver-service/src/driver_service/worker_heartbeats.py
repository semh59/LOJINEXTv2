"""Utility for recording worker heartbeats in the database."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from driver_service.models import WorkerHeartbeat


async def record_worker_heartbeat(
    session: AsyncSession,
    worker_name: str,
    status: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Record a worker's heartbeat in the database using an UPSERT."""
    now = datetime.now(timezone.utc)
    metadata_json = json.dumps(metadata) if metadata else None

    stmt = (
        insert(WorkerHeartbeat)
        .values(
            worker_name=worker_name,
            last_heartbeat_at_utc=now,
            worker_status=status,
            worker_metadata_json=metadata_json,
        )
        .on_conflict_do_update(
            index_elements=["worker_name"],
            set_={
                "last_heartbeat_at_utc": now,
                "worker_status": status,
                "worker_metadata_json": metadata_json,
            },
        )
    )

    await session.execute(stmt)
    # We don't commit here as heartbeats are usually part of a larger unit of work or a short-lived session.
