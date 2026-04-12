"""Driver Service FastAPI application entry point."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from driver_service.broker import create_broker
from driver_service.config import settings, validate_prod_settings
from driver_service.database import engine
from driver_service.errors import (
    ProblemDetailError,
    problem_detail_handler,
    validation_exception_handler,
)
from driver_service.middleware import PrometheusMiddleware, RequestIdMiddleware
from driver_service.routers.health import router as health_router
from driver_service.routers.import_jobs import router as import_jobs_router
from driver_service.routers.internal import router as internal_router
from driver_service.routers.lifecycle import router as lifecycle_router
from driver_service.routers.maintenance import close_http_client, router as maintenance_router
from driver_service.routers.public import router as public_router

logger = logging.getLogger("driver_service")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    from driver_service.observability import setup_logging
    from driver_service.redis_client import setup_redis
    from platform_common import setup_tracing, instrument_app, shutdown_tracing

    setup_logging(logging.INFO)
    validate_prod_settings(settings)

    # Initialise Core Platform Components
    setup_tracing(
        service_name="driver-service",
        service_version="0.1.0",
        environment=settings.environment,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
    )
    instrument_app(app)
    await setup_redis()

    broker = create_broker(settings.resolved_broker_type)
    app.state.broker = broker

    logger.info(
        "Driver Service starting on port %s (env=%s, broker=%s)",
        settings.service_port,
        settings.environment,
        settings.resolved_broker_type,
    )

    yield

    await broker.close()
    from driver_service.redis_client import close_redis

    await close_redis()
    shutdown_tracing()
    await close_http_client()
    await engine.dispose()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Driver Service",
    version="0.1.0",
    description="Canonical driver master data, lifecycle, search, and import",
    lifespan=lifespan,
)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(PrometheusMiddleware)

app.add_exception_handler(ProblemDetailError, problem_detail_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]

# Routers
app.include_router(health_router)
app.include_router(public_router)
app.include_router(lifecycle_router)
app.include_router(internal_router)
app.include_router(import_jobs_router)
app.include_router(maintenance_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "driver_service.main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=True,
    )
