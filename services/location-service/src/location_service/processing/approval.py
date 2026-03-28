"""Approval Flow Logic (Section 6.10).

Handles the promotion of calculated drafts to active route versions.
"""

import logging
from uuid import UUID

from sqlalchemy import select, update

from location_service.database import async_session_factory
from location_service.enums import DirectionCode, PairStatus, ProcessingStatus
from location_service.models import Route, RoutePair, RouteVersion

logger = logging.getLogger(__name__)


async def approve_route_versions(pair_id: UUID) -> None:
    """Atomic promotion of pending draft versions to ACTIVE.

    1. Mark current ACTIVE versions as SUPERSEDED.
    2. Mark pending CALCULATED_DRAFT versions as ACTIVE.
    3. Update RoutePair pointers and clear pending.
    """
    async with async_session_factory() as session:
        # 1. Fetch Pair with pessimistic lock
        pair = await session.get(RoutePair, pair_id, with_for_update=True)
        if not pair:
            raise ValueError(f"Route pair {pair_id} not found")

        # FINDING-11: Cannot approve a soft-deleted pair
        if pair.pair_status == PairStatus.SOFT_DELETED:
            raise ValueError(f"Route pair {pair_id} is soft-deleted and cannot be approved")

        if pair.pending_forward_version_no is None or pair.pending_reverse_version_no is None:
            raise ValueError(f"Route pair {pair_id} has no pending versions to approve")

        # 2. Get Routes
        routes_stmt = select(Route).where(Route.route_pair_id == pair_id)
        routes = (await session.execute(routes_stmt)).scalars().all()

        for route in routes:
            # A. Supersede current ACTIVE version
            await session.execute(
                update(RouteVersion)
                .where(
                    RouteVersion.route_id == route.route_id,
                    RouteVersion.processing_status == ProcessingStatus.ACTIVE,
                )
                .values(processing_status=ProcessingStatus.SUPERSEDED)
            )

            # B. Promote Pending DRAFT to ACTIVE
            pending_ver_no = (
                pair.pending_forward_version_no
                if route.direction == DirectionCode.FORWARD
                else pair.pending_reverse_version_no
            )

            await session.execute(
                update(RouteVersion)
                .where(
                    RouteVersion.route_id == route.route_id,
                    RouteVersion.version_no == pending_ver_no,
                )
                .values(processing_status=ProcessingStatus.ACTIVE)
            )

        # 3. Update Pair Pointers
        pair.current_active_forward_version_no = pair.pending_forward_version_no
        pair.current_active_reverse_version_no = pair.pending_reverse_version_no
        pair.pending_forward_version_no = None
        pair.pending_reverse_version_no = None
        pair.pair_status = PairStatus.ACTIVE

        await session.commit()
        logger.info(f"Successfully approved versions for pair {pair_id}")
