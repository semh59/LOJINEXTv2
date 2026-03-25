"""Approval API endpoints (Section 7.11-7.15)."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from location_service.database import get_db
from location_service.enums import PairStatus, ProcessingStatus
from location_service.errors import (
    route_pair_no_pending_draft,
    route_pair_not_found,
    route_pair_not_ready_for_approval,
)
from location_service.models import RoutePair, RouteVersion
from location_service.schemas import PairResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/pairs", tags=["Approval"])


@router.post("/{pair_id}/activate", response_model=PairResponse)
async def activate_route_pair_draft(
    pair_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
) -> PairResponse:
    """Promote pending directional drafts to ACTIVE status."""
    pair = await db.get(RoutePair, pair_id)
    if not pair:
        raise route_pair_not_found(str(pair_id))

    if pair.pending_forward_version_no is None or pair.pending_reverse_version_no is None:
        raise route_pair_not_ready_for_approval()

    # 1. Supersede current active versions if they exist
    if pair.current_active_forward_version_no:
        old_f_stmt = select(RouteVersion).where(
            RouteVersion.route_id == pair.forward_route_id,
            RouteVersion.version_no == pair.current_active_forward_version_no,
        )
        old_f = (await db.execute(old_f_stmt)).scalar_one_or_none()
        if old_f:
            old_f.processing_status = ProcessingStatus.SUPERSEDED

    if pair.current_active_reverse_version_no:
        old_r_stmt = select(RouteVersion).where(
            RouteVersion.route_id == pair.reverse_route_id,
            RouteVersion.version_no == pair.current_active_reverse_version_no,
        )
        old_r = (await db.execute(old_r_stmt)).scalar_one_or_none()
        if old_r:
            old_r.processing_status = ProcessingStatus.SUPERSEDED

    # 2. Activate pending versions
    new_f_stmt = select(RouteVersion).where(
        RouteVersion.route_id == pair.forward_route_id,
        RouteVersion.version_no == pair.pending_forward_version_no,
    )
    new_f = (await db.execute(new_f_stmt)).scalar_one_or_none()
    if new_f:
        new_f.processing_status = ProcessingStatus.ACTIVE

    new_r_stmt = select(RouteVersion).where(
        RouteVersion.route_id == pair.reverse_route_id,
        RouteVersion.version_no == pair.pending_reverse_version_no,
    )
    new_r = (await db.execute(new_r_stmt)).scalar_one_or_none()
    if new_r:
        new_r.processing_status = ProcessingStatus.ACTIVE

    # 3. Update Pair pointers
    pair.current_active_forward_version_no = pair.pending_forward_version_no
    pair.current_active_reverse_version_no = pair.pending_reverse_version_no
    pair.pending_forward_version_no = None
    pair.pending_reverse_version_no = None
    pair.pair_status = PairStatus.ACTIVE

    await db.commit()
    await db.refresh(pair)

    return PairResponse.model_validate(pair)


@router.post("/{pair_id}/discard", status_code=status.HTTP_204_NO_CONTENT)
async def discard_route_pair_draft(
    pair_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Discard pending directional drafts without activating them."""
    pair = await db.get(RoutePair, pair_id)
    if not pair:
        raise route_pair_not_found(str(pair_id))

    if pair.pending_forward_version_no is None:
        raise route_pair_no_pending_draft()

    # Mark versions as DISCARDED
    f_stmt = select(RouteVersion).where(
        RouteVersion.route_id == pair.forward_route_id,
        RouteVersion.version_no == pair.pending_forward_version_no,
    )
    f_ver = (await db.execute(f_stmt)).scalar_one_or_none()
    if f_ver:
        f_ver.processing_status = ProcessingStatus.DISCARDED

    r_stmt = select(RouteVersion).where(
        RouteVersion.route_id == pair.reverse_route_id,
        RouteVersion.version_no == pair.pending_reverse_version_no,
    )
    r_ver = (await db.execute(r_stmt)).scalar_one_or_none()
    if r_ver:
        r_ver.processing_status = ProcessingStatus.DISCARDED

    pair.pending_forward_version_no = None
    pair.pending_reverse_version_no = None

    await db.commit()
