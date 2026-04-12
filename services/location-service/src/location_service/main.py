"""Location Service FastAPI application entry point — standardized with tracing."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from location_service.broker import create_broker
from location_service.config import settings, validate_prod_settings
from location_service.database import engine

# Correct router imports based on filesystem audit
from location_service.routers.health import router as health_router
from location_service.routers.approval import router as approval_router
from location_service.routers.bulk_refresh import router as bulk_refresh_router
from location_service.routers.internal_routes import router as internal_router
from location_service.routers.pairs import router as pairs_router
from location_service.routers.points import router as points_router
from location_service.routers.processing import router as processing_router
from location_service.routers.routes_public import router as public_router

logger = logging.getLogger("location_service")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifetime: startup and shutdown hooks."""
    from location_service.observability import setup_logging
    from platform_common import setup_tracing, instrument_app, shutdown_tracing

    setup_logging(logging.INFO)
    validate_prod_settings(settings)

    # Initialise Core Platform Components
    setup_tracing(
        service_name="location-service",
        service_version="0.1.0",
        environment=settings.environment,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
    )
    instrument_app(app)

    broker = create_broker()
    app.state.broker = broker

    logger.info(
        "Location Service starting on port %s (env=%s, broker=%s)",
        settings.service_port,
        settings.environment,
        "kafka" if settings.kafka_bootstrap_servers else "log/noop",
    )

    yield

    await broker.close()
    shutdown_tracing()
    await engine.dispose()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Location Service",
    version="0.1.0",
    description="Routing, Geocoding and Parity validation for LOJINEXT",
    lifespan=lifespan,
    docs_url=None if settings.environment == "prod" else "/docs",
    redoc_url=None if settings.environment == "prod" else "/redoc",
)


@app.get("/", tags=["Root"])
async def root():
    """Service information endpoint."""
    return {
        "service": "location-service",
        "version": "0.1.0",
        "env": settings.environment,
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global catch-all for unhandled exceptions."""
    del request
    logger.exception("Unhandled exception level=CRITICAL")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error occurred.", "type": type(exc).__name__},
    )


# Register all standard routers
app.include_router(health_router)
app.include_router(public_router)
app.include_router(internal_router)
app.include_router(pairs_router)
app.include_router(points_router)
app.include_router(processing_router)
app.include_router(approval_router)
app.include_router(bulk_refresh_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "location_service.main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=True,
    )
