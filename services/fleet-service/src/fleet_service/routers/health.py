"""Health and readiness endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from fleet_service.auth import auth_outbound_status, auth_verify_status
from fleet_service.config import settings
from fleet_service.database import async_session_factory
from fleet_service.worker_heartbeats import get_worker_heartbeat_snapshot

logger = logging.getLogger("fleet_service.routers.health")

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe that only reflects process health."""
    return {"status": "ok", "service": "fleet-service"}


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    """Readiness probe that only passes when critical dependencies are healthy."""
    checks: dict[str, str] = {}
    ready_state = True

    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = "fail"
        ready_state = False
        logger.warning("Readiness: DB check failed: %s", exc)

    broker = getattr(request.app.state, "broker", None)
    if broker is None:
        checks["broker"] = "missing"
        ready_state = False
    else:
        broker_health_check = getattr(broker, "check_health", None)
        if broker_health_check is None:
            checks["broker"] = "ok"
        else:
            try:
                await broker_health_check()
                checks["broker"] = "ok"
            except Exception as exc:
                checks["broker"] = "fail"
                ready_state = False
                logger.warning("Readiness: broker check failed: %s", exc)

    for worker_name, check_name in (("outbox-relay", "outbox_relay"), ("fleet-worker", "worker")):
        try:
            heartbeat = await get_worker_heartbeat_snapshot(
                worker_name,
                stale_after_seconds=settings.heartbeat_stale_seconds,
            )
            checks[check_name] = heartbeat.status
            if heartbeat.status != "ok":
                ready_state = False
        except Exception as exc:
            checks[check_name] = "fail"
            ready_state = False
            logger.warning("Readiness: worker heartbeat check failed for %s: %s", worker_name, exc)

    checks["auth_verify"] = auth_verify_status()
    if checks["auth_verify"] != "ok":
        ready_state = False

    checks["auth_outbound"] = auth_outbound_status()
    if checks["auth_outbound"] not in {"ok", "cold"}:
        ready_state = False

    return JSONResponse(
        status_code=200 if ready_state else 503,
        content={
            "status": "ready" if ready_state else "not_ready",
            "service": "fleet-service",
            "checks": checks,
        },
    )
