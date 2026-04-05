"""Health and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from identity_service.crypto import require_kek_bytes, require_kek_version
from identity_service.database import get_session
from identity_service.token_service import ensure_active_signing_key, seed_bootstrap_state

router = APIRouter(tags=["identity-health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(session: AsyncSession = Depends(get_session)) -> JSONResponse:
    """Readiness probe."""
    checks: dict[str, str] = {}
    ready_state = True

    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "fail"
        ready_state = False

    try:
        require_kek_bytes()
        require_kek_version()
        checks["kek"] = "ok"
    except Exception:
        checks["kek"] = "fail"
        ready_state = False

    if ready_state:
        try:
            await seed_bootstrap_state(session)
            await ensure_active_signing_key(session)
            await session.commit()
            checks["bootstrap"] = "ok"
            checks["signing_key"] = "ok"
        except Exception:
            await session.rollback()
            checks["bootstrap"] = "fail"
            checks["signing_key"] = "fail"
            ready_state = False

    return JSONResponse(
        status_code=200 if ready_state else 503,
        content={"status": "ready" if ready_state else "not_ready", "checks": checks},
    )
