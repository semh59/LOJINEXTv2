"""Import API endpoints (Section 7.22)."""

import logging

from fastapi import APIRouter, File, UploadFile, status

from location_service.errors import import_file_too_large, import_unsupported_file_type
from location_service.processing.import_logic import process_import_csv

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/import", tags=["Bulk Operations"])

# FINDING-13: Align with errors.py docstring — 20MB limit
IMPORT_MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024
ALLOWED_EXTENSIONS = (".csv",)


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
)
async def import_route_pairs(
    file: UploadFile = File(...),
):
    """Import Route Pairs from CSV file (max 20MB).

    Returns per-row success/failure detail.
    """
    # FINDING-13: Validate file type with correct ProblemDetailError
    filename = file.filename or ""
    if not any(filename.endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise import_unsupported_file_type()

    content = await file.read()

    # FINDING-13: Enforce file size limit
    if len(content) > IMPORT_MAX_FILE_SIZE_BYTES:
        raise import_file_too_large()

    result = await process_import_csv(content)

    return {
        "status": "COMPLETED",
        "processed_rows": result.total_rows,
        "success_count": result.success_count,
        "failure_count": result.failure_count,
        "errors": [{"row": r, "message": m} for r, m in result.errors[:50]],
    }
