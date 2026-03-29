"""Health and readiness endpoints."""

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from location_service.config import settings
from location_service.database import async_session_factory

logger = logging.getLogger("location_service.health")

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe that only checks whether the process is running."""
    return {"status": "ok", "service": settings.service_name}


@router.get("/ready")
async def ready() -> JSONResponse:
    """Readiness probe that checks the database and required provider config."""
    checks: dict[str, object] = {}

    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        logger.warning("Readiness check failed: database - %s", exc)
        checks["database"] = "unavailable"

    checks["mapbox"] = "ok" if settings.mapbox_api_key else "missing"
    if settings.enable_ors_validation:
        checks["ors_api_key"] = "ok" if settings.ors_api_key else "missing"
        checks["ors_base_url"] = "ok" if settings.ors_base_url else "missing"
    else:
        checks["ors_validation"] = "disabled"

    all_ok = checks.get("database") == "ok" and checks.get("mapbox") == "ok"
    if settings.enable_ors_validation:
        all_ok = all_ok and checks.get("ors_api_key") == "ok" and checks.get("ors_base_url") == "ok"

    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={
            "status": "ready" if all_ok else "not_ready",
            "checks": checks,
        },
    )
