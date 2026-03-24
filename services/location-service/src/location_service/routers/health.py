"""Health and readiness endpoints.

Implements v0.7 Section 14 — liveness and readiness probes.
"""

import logging

from fastapi import APIRouter
from sqlalchemy import text

from location_service.config import settings
from location_service.database import async_session_factory

logger = logging.getLogger("location_service.health")

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe — always returns 200 if process is running."""
    return {"status": "ok", "service": settings.service_name}


@router.get("/ready")
async def ready() -> dict[str, object]:
    """Readiness probe — checks database connectivity and critical config."""
    checks: dict[str, object] = {}

    # Database check
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        logger.warning("Readiness check failed: database — %s", exc)
        checks["database"] = f"error: {exc}"

    # Config checks
    checks["mapbox_api_key"] = "configured" if settings.mapbox_api_key else "MISSING"
    checks["ors_base_url"] = "configured" if settings.ors_base_url else "not_configured"

    all_ok = checks.get("database") == "ok" and checks.get("mapbox_api_key") == "configured"

    return {
        "status": "ready" if all_ok else "not_ready",
        "checks": checks,
    }
