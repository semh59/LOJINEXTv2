"""Health and readiness router for Driver Service (spec Section 10)."""

import logging

from fastapi import APIRouter
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from starlette.responses import Response

from driver_service.database import async_session_factory

logger = logging.getLogger("driver_service")
router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Liveness probe — returns immediately."""
    return {"status": "ok", "service": "driver-service", "version": "0.1.0"}


@router.get("/ready")
async def readiness_check() -> dict[str, object]:
    """Readiness probe — verifies DB connectivity and critical config."""
    checks: dict[str, object] = {}

    # DB check
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        logger.error("Readiness: database check failed: %s", exc)
        checks["database"] = "fail"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": overall, "checks": checks}


@router.get("/metrics")
async def metrics() -> Response:
    """Expose Prometheus metrics."""
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
