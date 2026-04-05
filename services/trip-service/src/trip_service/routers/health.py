"""Health and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from trip_service.auth import auth_outbound_status, auth_verify_status
from trip_service.config import settings
from trip_service.database import async_session_factory
from trip_service.worker_heartbeats import get_worker_heartbeat_snapshot

router = APIRouter(prefix="/v1", tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Process liveness only."""
    return {"status": "ok"}


@router.get("/metrics")
async def metrics() -> Response:
    """Expose Prometheus metrics for internal scraping."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/ready")
async def readiness(request: Request) -> JSONResponse:
    """Readiness with hard dependency checks only."""
    checks: dict[str, str] = {}
    overall = True

    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"
        overall = False

    broker = getattr(request.app.state, "broker", None)
    if broker is None:
        checks["broker"] = "unavailable"
        overall = False
    else:
        try:
            await broker.check_health()
            checks["broker"] = "ok"
        except Exception:
            checks["broker"] = "unavailable"
            overall = False

    checks["auth_verify"] = auth_verify_status()
    overall = overall and checks["auth_verify"] == "ok"

    checks["auth_outbound"] = auth_outbound_status()
    overall = overall and checks["auth_outbound"] in {"ok", "cold"}

    enrichment_heartbeat = await get_worker_heartbeat_snapshot(
        "enrichment-worker",
        stale_after_seconds=settings.worker_heartbeat_timeout_seconds,
    )
    checks["enrichment_worker"] = enrichment_heartbeat.status
    overall = overall and enrichment_heartbeat.status == "ok"

    outbox_heartbeat = await get_worker_heartbeat_snapshot(
        "outbox-relay",
        stale_after_seconds=settings.worker_heartbeat_timeout_seconds,
    )
    checks["outbox_relay"] = outbox_heartbeat.status
    overall = overall and outbox_heartbeat.status == "ok"

    cleanup_heartbeat = await get_worker_heartbeat_snapshot(
        "cleanup-worker",
        stale_after_seconds=settings.worker_heartbeat_timeout_seconds,
    )
    checks["cleanup_worker"] = cleanup_heartbeat.status
    overall = overall and cleanup_heartbeat.status == "ok"

    return JSONResponse(
        status_code=200 if overall else 503,
        content={
            "status": "ready" if overall else "not_ready",
            "checks": checks,
        },
    )
