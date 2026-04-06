"""Approval flow logic for promoting or discarding pending drafts."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from location_service.audit_helpers import (
    _write_audit,
    _write_outbox,
)
from location_service.audit_helpers import (
    serialize_pair_audit as serialize_pair,
)
from location_service.database import async_session_factory
from location_service.enums import DirectionCode, PairStatus, ProcessingStatus
from location_service.models import (
    Route,
    RoutePair,
    RouteVersion,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _session_scope(session: AsyncSession | None) -> AsyncIterator[AsyncSession]:
    """Yield the provided session or create a managed session for the operation."""
    if session is not None:
        yield session
        return

    async with async_session_factory() as managed_session:
        yield managed_session


async def _get_locked_pair(session: AsyncSession, pair_id: str) -> RoutePair:
    """Load and lock the pair row for approval/discard mutations."""
    pair = await session.get(RoutePair, pair_id, with_for_update=True)
    if pair is None:
        raise ValueError(f"Route pair {pair_id} not found")
    if pair.pair_status == PairStatus.SOFT_DELETED:
        raise ValueError(f"Route pair {pair_id} is soft-deleted and cannot be modified")
    return pair


async def _get_routes_by_direction(session: AsyncSession, pair_id: str) -> dict[DirectionCode, Route]:
    """Return the pair routes keyed by direction, or raise if incomplete."""
    routes = (await session.execute(select(Route).where(Route.route_pair_id == pair_id))).scalars().all()
    route_map = {DirectionCode(route.direction): route for route in routes}
    if DirectionCode.FORWARD not in route_map or DirectionCode.REVERSE not in route_map:
        raise ValueError(f"Route pair {pair_id} is missing directional routes")
    return route_map


async def approve_route_versions(pair_id: str, *, session: AsyncSession | None = None) -> RoutePair:
    """Atomically promote pending draft versions to ACTIVE and return the pair."""
    async with _session_scope(session) as active_session:
        pair = await _get_locked_pair(active_session, pair_id)
        if pair.pending_forward_version_no is None or pair.pending_reverse_version_no is None:
            raise ValueError(f"Route pair {pair_id} has no pending versions to approve")

        route_map = await _get_routes_by_direction(active_session, pair_id)
        forward_route = route_map[DirectionCode.FORWARD]
        reverse_route = route_map[DirectionCode.REVERSE]

        await active_session.execute(
            update(RouteVersion)
            .where(
                RouteVersion.route_id.in_([forward_route.route_id, reverse_route.route_id]),
                RouteVersion.processing_status == ProcessingStatus.ACTIVE,
            )
            .values(processing_status=ProcessingStatus.SUPERSEDED)
        )

        await active_session.execute(
            update(RouteVersion)
            .where(
                RouteVersion.route_id == forward_route.route_id,
                RouteVersion.version_no == pair.pending_forward_version_no,
            )
            .values(processing_status=ProcessingStatus.ACTIVE)
        )
        await active_session.execute(
            update(RouteVersion)
            .where(
                RouteVersion.route_id == reverse_route.route_id,
                RouteVersion.version_no == pair.pending_reverse_version_no,
            )
            .values(processing_status=ProcessingStatus.ACTIVE)
        )

        pair.forward_route_id = forward_route.route_id
        pair.reverse_route_id = reverse_route.route_id
        pair.current_active_forward_version_no = pair.pending_forward_version_no
        pair.current_active_reverse_version_no = pair.pending_reverse_version_no
        pair.pending_forward_version_no = None
        pair.pending_reverse_version_no = None
        pair.pair_status = PairStatus.ACTIVE
        pair.row_version += 1

        # NEW: Phase 3 Audit & Outbox
        new_snapshot = serialize_pair(pair)
        await _write_audit(
            session=active_session,
            target_type="PAIR",
            target_id=str(pair.route_pair_id),
            action_type="APPROVE",
            actor_id="SYSTEM",
            actor_role="MANAGER",
            new_snapshot=new_snapshot,
        )
        await _write_outbox(
            session=active_session,
            event_name="location.route.activated.v1",
            payload={
                "pair_id": str(pair.route_pair_id),
                "pair_code": pair.pair_code,
                "forward_route_id": str(pair.forward_route_id),
                "reverse_route_id": str(pair.reverse_route_id),
                "occurred_at_utc": datetime.now(UTC).isoformat(),
            },
        )

        await active_session.commit()
        logger.info("Approved route versions for pair %s", pair_id)
        return pair


async def discard_route_versions(pair_id: str, *, session: AsyncSession | None = None) -> RoutePair:
    """Discard pending draft versions for a pair and return the pair."""
    async with _session_scope(session) as active_session:
        pair = await _get_locked_pair(active_session, pair_id)
        if pair.pending_forward_version_no is None or pair.pending_reverse_version_no is None:
            raise ValueError(f"Route pair {pair_id} has no pending versions to discard")

        route_map = await _get_routes_by_direction(active_session, pair_id)
        await active_session.execute(
            update(RouteVersion)
            .where(
                RouteVersion.route_id == route_map[DirectionCode.FORWARD].route_id,
                RouteVersion.version_no == pair.pending_forward_version_no,
            )
            .values(processing_status=ProcessingStatus.DISCARDED)
        )
        await active_session.execute(
            update(RouteVersion)
            .where(
                RouteVersion.route_id == route_map[DirectionCode.REVERSE].route_id,
                RouteVersion.version_no == pair.pending_reverse_version_no,
            )
            .values(processing_status=ProcessingStatus.DISCARDED)
        )

        pair.pending_forward_version_no = None
        pair.pending_reverse_version_no = None
        pair.row_version += 1

        # NEW: Phase 3 Audit & Outbox
        await _write_audit(
            session=active_session,
            target_type="PAIR",
            target_id=str(pair.route_pair_id),
            action_type="DISCARD",
            actor_id="SYSTEM",
            actor_role="MANAGER",
        )
        await _write_outbox(
            session=active_session,
            event_name="location.route.discarded.v1",
            payload={
                "pair_id": str(pair.route_pair_id),
                "pair_code": pair.pair_code,
                "occurred_at_utc": datetime.now(UTC).isoformat(),
            },
        )

        await active_session.commit()
        logger.info("Discarded pending route versions for pair %s", pair_id)
        return pair
