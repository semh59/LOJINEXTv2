"""Exact 404 tombstones for removed trip-service endpoints."""

from fastapi import APIRouter

from trip_service.errors import endpoint_removed

router = APIRouter(tags=["removed-endpoints"])


@router.post("/api/v1/trips/import-files")
async def removed_import_files() -> None:
    """Return an exact 404 for the removed import file endpoint."""
    raise endpoint_removed()


@router.post("/api/v1/trips/import-jobs")
async def removed_import_jobs_create() -> None:
    """Return an exact 404 for the removed import jobs create endpoint."""
    raise endpoint_removed()


@router.get("/api/v1/trips/import-jobs/{job_id}")
async def removed_import_jobs_detail(job_id: str) -> None:
    """Return an exact 404 for the removed import jobs detail endpoint."""
    raise endpoint_removed()


@router.post("/api/v1/trips/export-jobs")
async def removed_export_jobs_create() -> None:
    """Return an exact 404 for the removed export jobs create endpoint."""
    raise endpoint_removed()


@router.get("/api/v1/trips/export-jobs/{job_id}")
async def removed_export_jobs_detail(job_id: str) -> None:
    """Return an exact 404 for the removed export jobs detail endpoint."""
    raise endpoint_removed()


@router.get("/api/v1/trips/export-jobs/{job_id}/download")
async def removed_export_jobs_download(job_id: str) -> None:
    """Return an exact 404 for the removed export jobs download endpoint."""
    raise endpoint_removed()


@router.delete("/api/v1/trips/{trip_id}/hard")
async def removed_legacy_hard_delete(trip_id: str) -> None:
    """Return an exact 404 for the removed legacy hard-delete endpoint."""
    raise endpoint_removed()
