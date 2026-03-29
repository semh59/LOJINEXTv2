"""Approval API endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from location_service.database import get_db
from location_service.errors import (
    route_pair_no_pending_draft,
    route_pair_not_found,
    route_pair_not_ready_for_approval,
    route_pair_soft_deleted,
    route_pair_version_mismatch,
)
from location_service.middleware import check_version_match, set_etag
from location_service.models import RoutePair
from location_service.processing.approval import approve_route_versions, discard_route_versions
from location_service.routers.pairs import _get_pair_detail, serialize_pair
from location_service.schemas import PairResponse

router = APIRouter(prefix="/v1/pairs", tags=["approval"])


def _raise_from_approval_error(pair_id: UUID, exc: ValueError, *, discard: bool = False) -> None:
    """Translate approval flow ValueError messages into stable API problems."""
    message = str(exc)
    if "not found" in message:
        raise route_pair_not_found(str(pair_id))
    if "soft-deleted" in message:
        raise route_pair_soft_deleted()
    if "no pending versions" in message:
        if discard:
            raise route_pair_no_pending_draft()
        raise route_pair_not_ready_for_approval()
    raise exc


@router.post("/{pair_id}/approve", response_model=PairResponse)
async def approve_route_pair_draft(
    request: Request,
    response: Response,
    pair_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
) -> PairResponse:
    """Promote pending directional drafts to ACTIVE status."""
    pair = await db.get(RoutePair, pair_id)
    if pair is None:
        raise route_pair_not_found(str(pair_id))
    check_version_match(request, pair.row_version, mismatch_factory=route_pair_version_mismatch)

    try:
        await approve_route_versions(pair_id, session=db)
    except ValueError as exc:
        _raise_from_approval_error(pair_id, exc)

    pair, origin, destination = await _get_pair_detail(db, pair_id)
    set_etag(response, pair.row_version)
    return serialize_pair(pair, origin, destination)


@router.post("/{pair_id}/discard", response_model=PairResponse)
async def discard_route_pair_draft(
    request: Request,
    response: Response,
    pair_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
) -> PairResponse:
    """Discard pending directional drafts without activating them."""
    pair = await db.get(RoutePair, pair_id)
    if pair is None:
        raise route_pair_not_found(str(pair_id))
    check_version_match(request, pair.row_version, mismatch_factory=route_pair_version_mismatch)

    try:
        await discard_route_versions(pair_id, session=db)
    except ValueError as exc:
        _raise_from_approval_error(pair_id, exc, discard=True)

    pair, origin, destination = await _get_pair_detail(db, pair_id)
    set_etag(response, pair.row_version)
    return serialize_pair(pair, origin, destination)
