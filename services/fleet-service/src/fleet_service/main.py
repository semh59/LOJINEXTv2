"""Fleet Service FastAPI application entry point."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from fleet_service.broker import create_broker
from fleet_service.config import settings, validate_prod_settings
from fleet_service.database import engine
from fleet_service.errors import (
    ProblemDetailError,
    problem_detail_handler,
    validation_exception_handler,
)
from fleet_service.middleware import PrometheusMiddleware, RequestIdMiddleware

logger = logging.getLogger("fleet_service")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    from platform_common import instrument_app, setup_logging, setup_tracing, shutdown_tracing

    from fleet_service.redis_client import setup_redis

    setup_logging(logging.INFO)
    validate_prod_settings(settings)

    # Initialise Core Platform Components
    setup_tracing(
        service_name="fleet-service",
        service_version="0.1.0",
        environment=settings.environment,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
    )
    instrument_app(app)
    await setup_redis()

    logger.info(
        "Fleet Service starting on port %s (env=%s, broker=%s)",
        settings.service_port,
        settings.environment,
        settings.resolved_broker_type,
    )
    broker = create_broker(settings.resolved_broker_type)
    app.state.broker = broker

    try:
        yield
    finally:
        from fleet_service.clients import driver_client, trip_client
        from fleet_service.redis_client import close_redis

        await driver_client.close()
        await trip_client.close()
        await broker.close()
        await close_redis()
        shutdown_tracing()
        await engine.dispose()
        logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """Factory function for creating the Fleet Service FastAPI application."""
    application = FastAPI(
        title="Fleet Service",
        version="0.1.0",
        description="Canonical vehicle and trailer master data, lifecycle, technical specs, and asset validation",
        lifespan=lifespan,
    )

    from fleet_service.observability import HTTP_REQUESTS_TOTAL, REQUEST_DURATION, get_standard_labels
    application.add_middleware(RequestIdMiddleware)
    application.add_middleware(
        PrometheusMiddleware,
        requests_counter=HTTP_REQUESTS_TOTAL,
        duration_histogram=REQUEST_DURATION,
        label_provider=get_standard_labels,
    )

    application.add_exception_handler(ProblemDetailError, problem_detail_handler)  # type: ignore[arg-type]
    application.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]

    # Health/readiness routes (always available)
    from fleet_service.routers.health import router as health_router

    application.include_router(health_router)

    # Vehicle CRUD + lifecycle routes (Phase C)
    from fleet_service.routers.vehicle_router import router as vehicle_router

    application.include_router(vehicle_router)

    # Vehicle Spec Version routes (Phase D)
    from fleet_service.routers.vehicle_spec_router import router as vehicle_spec_router

    application.include_router(vehicle_spec_router)

    # Trailer CRUD + lifecycle + spec routes (Phase E)
    from fleet_service.routers.trailer_router import router as trailer_router

    application.include_router(trailer_router)

    # Internal service-to-service routes (Phase F)
    from fleet_service.routers.internal_router import router as internal_router

    application.include_router(internal_router)

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "fleet_service.main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=True,
    )
