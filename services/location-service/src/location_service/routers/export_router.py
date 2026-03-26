"""Export API endpoints (Section 7.22)."""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from location_service.processing.export_logic import generate_export_csv_stream

router = APIRouter(prefix="/v1/export", tags=["Bulk Operations"])


@router.get(
    "",
    response_class=StreamingResponse,
)
async def export_route_pairs():
    """Stream all Route Pairs as CSV."""
    return StreamingResponse(
        generate_export_csv_stream(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=route_pairs_export.csv"},
    )
