import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from location_service.auth import auth_verify_status
from location_service.config import settings
from location_service.database import async_session_factory
from location_service.provider_health import get_provider_probe_result, provider_probe_age_seconds
from location_service.worker_heartbeats import get_worker_heartbeat_snapshot

logger = logging.getLogger("location_service.health")

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe that only checks whether the process is running."""
    return {"status": "ok", "service": settings.service_name}


@router.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics scrape endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    """Readiness probe that checks the database, broker, and required provider config."""
    checks: dict[str, object] = {}

    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        logger.warning("Readiness check failed: database - %s", exc)
        checks["database"] = "unavailable"

    broker = getattr(request.app.state, "broker", None)
    if broker is None:
        checks["broker"] = "unavailable"
    else:
        try:
            await broker.check_health()
            checks["broker"] = "ok"
        except Exception as exc:
            logger.warning("Readiness check failed: broker - %s", exc)
            checks["broker"] = "unavailable"

    probe_result = await get_provider_probe_result()

    checks["mapbox"] = "ok" if settings.mapbox_api_key else "missing"
    checks["mapbox_live"] = probe_result.mapbox_live
    if settings.enable_ors_validation:
        checks["ors_api_key"] = "ok" if settings.ors_api_key else "missing"
        checks["ors_base_url"] = "ok" if settings.ors_base_url else "missing"
        checks["ors_live"] = probe_result.ors_live
    else:
        checks["ors_validation"] = "disabled"
    checks["provider_probe_age_s"] = provider_probe_age_seconds(probe_result)
    checks["auth_verify"] = await auth_verify_status()

    worker_heartbeat = await get_worker_heartbeat_snapshot(
        "processing-worker",
        stale_after_seconds=settings.worker_heartbeat_timeout_seconds,
    )
    checks["processing_worker"] = worker_heartbeat.status

    # V2.1 Parity Patch: Allow bypassing provider health for testing with dummy keys
    ignore_providers = str(settings.ignore_provider_health).lower() == "true"

    all_ok = (
        checks.get("database") == "ok"
        and checks.get("broker") == "ok"
        and checks.get("auth_verify") == "ok"
        and checks.get("processing_worker") == "ok"
    )

    if not ignore_providers:
        all_ok = all_ok and checks.get("mapbox") == "ok" and checks.get("mapbox_live") == "ok"
        if settings.enable_ors_validation:
            all_ok = (
                all_ok
                and checks.get("ors_api_key") == "ok"
                and checks.get("ors_base_url") == "ok"
                and checks.get("ors_live") == "ok"
            )

    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={
            "status": "ready" if all_ok else "not_ready",
            "checks": checks,
        },
    )
