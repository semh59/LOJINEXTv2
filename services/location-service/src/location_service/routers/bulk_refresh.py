"""Bulk refresh API endpoints (Section 7.21)."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from location_service.database import get_db
from location_service.processing.bulk import trigger_bulk_refresh

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/bulk-refresh", tags=["Bulk Operations"])


class BulkRefreshRequest(BaseModel):
    """Request schema for triggering bulk refresh."""

    pair_ids: list[Annotated[str, Field(pattern="^[0-9a-fA-F-]{36}$")]] | None = Field(
        default=None, description="Optional list of pair UUIDs. If null, all active pairs are refreshed."
    )


@router.post(
    "/jobs",
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_bulk_refresh_job(
    request: BulkRefreshRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Trigger bulk refresh for selected or all active pairs (background job)."""
    pair_ids = None
    if request and request.pair_ids:
        import uuid

        pair_ids = [uuid.UUID(pid) for pid in request.pair_ids]

    triggered_count = await trigger_bulk_refresh(pair_ids=pair_ids)

    return {
        "status": "ACCEPTED",
        "triggered_count": triggered_count,
        "detail": f"Background processing triggered for {triggered_count} pairs.",
    }
