"""Timeline repository (Section 8.6 — immutable event log)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_service.models import FleetAssetTimelineEvent


async def insert_timeline_event(session: AsyncSession, event: FleetAssetTimelineEvent) -> None:
    """Insert a new timeline event."""
    session.add(event)
    await session.flush()


async def get_timeline_by_aggregate(
    session: AsyncSession,
    aggregate_type: str,
    aggregate_id: str,
    *,
    page: int = 1,
    per_page: int = 50,
) -> list[FleetAssetTimelineEvent]:
    """Fetch timeline events for an aggregate, ordered by occurred_at_utc DESC."""
    offset = (page - 1) * per_page
    stmt = (
        select(FleetAssetTimelineEvent)
        .where(
            FleetAssetTimelineEvent.aggregate_type == aggregate_type,
            FleetAssetTimelineEvent.aggregate_id == aggregate_id,
        )
        .order_by(FleetAssetTimelineEvent.occurred_at_utc.desc())
        .offset(offset)
        .limit(per_page)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
