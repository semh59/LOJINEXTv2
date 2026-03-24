"""Health and readiness endpoints.

V8 Sections 18.4–18.5.
"""

from fastapi import APIRouter
from sqlalchemy import text

from trip_service.database import async_session_factory

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """V8 Section 18.4 — Process liveness only."""
    return {"status": "ok"}


@router.get("/ready")
async def readiness() -> dict[str, object]:
    """V8 Section 18.5 — Readiness with hard and soft dependencies.

    Hard dependencies (must pass): DB, internal auth.
    Soft dependencies (may degrade): object storage, Weather, Location, Fleet.
    """
    checks: dict[str, str] = {}
    overall = True

    # Hard dependency: database
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"
        overall = False

    # Hard dependency: internal auth (stub — always ok for V1)
    checks["internal_auth"] = "ok"

    # Soft dependencies — not blocking startup
    checks["object_storage"] = "ok"  # checked lazily on use
    checks["weather_service"] = "degraded"  # soft
    checks["location_service"] = "degraded"  # soft
    checks["fleet_service"] = "degraded"  # soft

    status_code = 200 if overall else 503
    return {
        "status": "ready" if overall else "not_ready",
        "checks": checks,
        "_status_code": status_code,
    }
