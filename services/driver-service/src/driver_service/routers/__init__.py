"""Health and readiness router for Driver Service (spec Section 10)."""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from starlette.responses import JSONResponse, Response

from driver_service.auth import auth_outbound_status, auth_verify_status
from driver_service.config import settings
from driver_service.database import async_session_factory
from driver_service.models import WorkerHeartbeat

logger = logging.getLogger("driver_service")
router = APIRouter(prefix="/v1", tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Liveness probe that returns immediately."""
    return {"status": "ok", "service": "driver-service", "version": "0.1.0"}


@router.get("/ready")
async def readiness_check(request: Request) -> JSONResponse:
    """Readiness probe that checks broker wiring, DB connectivity, and worker freshness."""
    checks: dict[str, object] = {}
    ready = True

    broker = getattr(request.app.state, "broker", None)
    if broker is None:
        checks["broker"] = "missing"
        ready = False
    else:
        broker_health_check = getattr(broker, "check_health", None)
        if broker_health_check is None:
            checks["broker"] = "ok"
        else:
            try:
                broker_ok = bool(await broker_health_check())
            except Exception as exc:
                logger.error("Readiness: broker check failed: %s", exc)
                checks["broker"] = "fail"
                ready = False
            else:
                checks["broker"] = "ok" if broker_ok else "fail"
                if not broker_ok:
                    ready = False

    checks["auth_verify"] = auth_verify_status()
    if checks["auth_verify"] != "ok":
        ready = False

    checks["auth_outbound"] = auth_outbound_status()
    if checks["auth_outbound"] not in {"ok", "cold"}:
        ready = False

    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
            now = datetime.now(timezone.utc)

            worker_windows = {
                "outbox_relay": max(settings.outbox_poll_interval_seconds * 3, 15),
                "import_worker": max(settings.maintenance_poll_interval_seconds * 3, 30),
            }
            for worker_name, stale_after_seconds in worker_windows.items():
                heartbeat = await session.get(WorkerHeartbeat, worker_name)
                if heartbeat is None:
                    checks[worker_name] = "missing"
                    ready = False
                    continue
                if heartbeat.last_heartbeat_at_utc < now - timedelta(seconds=stale_after_seconds):
                    checks[worker_name] = "stale"
                    ready = False
                    continue
                if heartbeat.worker_status and heartbeat.worker_status.upper() not in {"RUNNING", "OK"}:
                    checks[worker_name] = heartbeat.worker_status.lower()
                    ready = False
                    continue
                checks[worker_name] = "ok"
        checks["database"] = "ok"
    except Exception as exc:
        logger.error("Readiness: database check failed: %s", exc)
        checks["database"] = "fail"
        ready = False

    status_code = 200 if ready else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "ready" if ready else "not_ready", "service": "driver-service", "checks": checks},
    )


@router.get("/metrics")
async def metrics() -> Response:
    """Expose Prometheus metrics."""
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
