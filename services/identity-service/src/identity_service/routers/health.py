"""Health and readiness endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from identity_service.broker import probe_broker
from identity_service.config import settings
from identity_service.database import get_session
from identity_service.models import IdentityWorkerHeartbeatModel
from identity_service.workers.outbox_relay import OUTBOX_WORKER_NAME

router = APIRouter(tags=["health"])


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@router.get("/health")
async def health() -> dict[str, str]:
    """Return a simple liveness probe."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(session: AsyncSession = Depends(get_session)) -> JSONResponse:
    """Report runtime dependency readiness for API traffic."""
    checks: dict[str, str] = {}
    ready_state = True

    database_ok = False
    try:
        await session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        checks["database"] = "failed"
        ready_state = False
    else:
        checks["database"] = "ok"
        database_ok = True

    broker_ok, _ = await probe_broker()
    if broker_ok:
        checks["broker"] = "ok"
    else:
        checks["broker"] = "failed"
        ready_state = False

    if database_ok:
        heartbeat = await session.get(IdentityWorkerHeartbeatModel, OUTBOX_WORKER_NAME)
        if heartbeat is None:
            checks["outbox_worker"] = "missing"
            ready_state = False
        else:
            last_seen = _as_utc(heartbeat.last_seen_at_utc)
            stale_after = timedelta(seconds=settings.outbox_worker_stale_after_seconds)
            if last_seen < datetime.now(UTC) - stale_after:
                checks["outbox_worker"] = "stale"
                ready_state = False
            else:
                checks["outbox_worker"] = "ok"
    else:
        checks["outbox_worker"] = "failed"

    payload = {
        "status": "ready" if ready_state else "not_ready",
        "checks": checks,
    }
    return JSONResponse(status_code=200 if ready_state else 503, content=payload)
