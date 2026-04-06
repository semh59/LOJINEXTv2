"""Bulk refresh API endpoints."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from location_service.auth import super_admin_auth_dependency
from location_service.database import get_db
from location_service.processing.bulk import trigger_bulk_refresh
from location_service.schemas import BulkRefreshTriggerRequest, BulkRefreshTriggerResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/bulk-refresh", tags=["bulk-refresh"])


@router.post(
    "/jobs",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=BulkRefreshTriggerResponse,
    dependencies=[Depends(super_admin_auth_dependency)],
)
async def create_bulk_refresh_job(
    db: Annotated[AsyncSession, Depends(get_db)],
    request: BulkRefreshTriggerRequest | None = None,
) -> BulkRefreshTriggerResponse:
    """Trigger bulk refresh for selected or all active pairs."""
    del db
    pair_ids = request.pair_ids if request else None
    triggered_count = await trigger_bulk_refresh(pair_ids=pair_ids)
    requested_pair_count = len(pair_ids) if pair_ids is not None else None
    detail = (
        f"Background processing triggered for {triggered_count} pairs."
        if triggered_count
        else "No eligible pairs matched the bulk refresh request."
    )
    return BulkRefreshTriggerResponse(
        status="ACCEPTED",
        triggered_count=triggered_count,
        requested_pair_count=requested_pair_count,
        detail=detail,
    )
