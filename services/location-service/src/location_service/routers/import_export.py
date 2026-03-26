"""Import/Export aggregator router (Section 7.22)."""

from fastapi import APIRouter

from location_service.routers import export_router, import_router

router = APIRouter()

router.include_router(import_router.router)
router.include_router(export_router.router)
