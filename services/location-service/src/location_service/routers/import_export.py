"""Import/Export API endpoints (Section 7.22-7.28)."""

import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from location_service.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/data", tags=["Import/Export"])


@router.post(
    "/import",
    status_code=status.HTTP_202_ACCEPTED,
)
async def import_data(
    db: AsyncSession = Depends(get_db),
):
    """Import locations from Excel/CSV."""
    # TODO: Implement import logic Section 6.13
    return {"message": "Import job starting (stub)"}


@router.post(
    "/export",
    status_code=status.HTTP_202_ACCEPTED,
)
async def export_data(
    db: AsyncSession = Depends(get_db),
):
    """Export locations/routes to Excel/CSV."""
    # TODO: Implement export logic Section 6.14
    return {"message": "Export job starting (stub)"}
