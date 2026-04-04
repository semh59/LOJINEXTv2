"""Health and readiness endpoints (Section 16.1–16.2)."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from sqlalchemy import text

from fleet_service.config import settings
from fleet_service.database import async_session_factory
from fleet_service.worker_heartbeats import get_worker_heartbeat_snapshot

logger = logging.getLogger("fleet_service.routers.health")

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe — always returns 200 if the process is alive."""
    return {"status": "ok", "service": "fleet-service"}


@router.get("/ready")
async def ready() -> dict:
    """Readiness probe — production logic.

    Checks:
    1. DB connectivity (SELECT 1)
    2. Worker heartbeat freshness
    """
    checks: dict[str, str] = {}
    overall = "ok"

    # DB connectivity
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"
        overall = "degraded"
        logger.warning("Readiness: DB check failed: %s", exc)

    # Worker heartbeat (outbox-relay)
    try:
        hb = await get_worker_heartbeat_snapshot(
            "outbox-relay",
            stale_after_seconds=settings.heartbeat_stale_seconds,
        )
        checks["outbox_relay"] = hb.status
        if hb.status != "ok":
            overall = "degraded"
    except Exception as exc:
        checks["outbox_relay"] = f"error: {exc}"
        overall = "degraded"

    return {"status": overall, "service": "fleet-service", "checks": checks}
