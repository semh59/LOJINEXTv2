"""Bulk refresh API endpoints (Section 7.21)."""

import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from location_service.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/bulk-refresh", tags=["Bulk Operations"])


@router.post(
    "/jobs",
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_bulk_refresh_job(
    db: AsyncSession = Depends(get_db),
):
    """Trigger bulk refresh for all active pairs (background job)."""
    # TODO: Implement bulk refresh logic Section 6.12
    return {"message": "Bulk refresh job queued (stub)"}
