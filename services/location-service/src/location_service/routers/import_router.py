"""Import API endpoints (Section 7.22)."""

import logging

from fastapi import APIRouter, File, UploadFile, status

from location_service.processing.import_logic import process_import_csv

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/import", tags=["Bulk Operations"])


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
)
async def import_route_pairs(
    file: UploadFile = File(...),
):
    """Import Route Pairs from CSV file (max 5MB)."""
    if not file.filename.endswith(".csv"):
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    content = await file.read()

    result = await process_import_csv(content)

    return {
        "status": "COMPLETED",
        "processed_rows": result.total_rows,
        "success_count": result.success_count,
        "failure_count": result.failure_count,
        "errors": [{"row": r, "message": m} for r, m in result.errors[:50]],  # Limit error list
    }
