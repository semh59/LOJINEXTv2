"""Bulk Refresh Orchestration (Section 4.4).

Coordinates the triggering of normative processing for multiple route pairs.
"""

import logging

from sqlalchemy import select

from location_service.database import async_session_factory
from location_service.enums import PairStatus, TriggerType
from location_service.models import RoutePair
from location_service.processing.pipeline import trigger_processing

logger = logging.getLogger(__name__)


async def trigger_bulk_refresh(pair_ids: list[str] | None = None) -> int:
    """Trigger background processing for a batch of pairs.

    If pair_ids is None, all ACTIVE pairs are targeted.
    Returns the count of triggered runs.
    """
    targets: list[str] = []

    async with async_session_factory() as session:
        if pair_ids is not None:
            # Validate IDs
            stmt = select(RoutePair.route_pair_id).where(RoutePair.route_pair_id.in_(pair_ids))
            targets = list((await session.execute(stmt)).scalars().all())
        else:
            # Target all ACTIVE
            stmt = select(RoutePair.route_pair_id).where(RoutePair.pair_status == PairStatus.ACTIVE)
            targets = list((await session.execute(stmt)).scalars().all())

    if not targets:
        logger.warning("Bulk refresh triggered but no target pairs found.")
        return 0

    # trigger_processing only enqueues the run; the dedicated worker drains the queue.
    for pid in targets:
        try:
            await trigger_processing(pair_id=pid, trigger_type=TriggerType.BULK_REFRESH_ITEM)
        except Exception as exc:
            logger.error("Failed to trigger refresh for pair %s: %s", pid, exc)
            continue

    logger.info("Successfully triggered bulk refresh for %s pairs.", len(targets))
    return len(targets)
