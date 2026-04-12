"""Trip Service FastAPI application entry point — standardized with platform-common."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from trip_service.broker import create_broker
from trip_service.config import settings, validate_prod_settings
from trip_service.database import engine
from trip_service.errors import (
    ProblemDetailError,
    problem_detail_handler,
    validation_exception_handler,
)
from trip_service.http_clients import close_http_clients
from trip_service.middleware import PrometheusMiddleware, RequestIdMiddleware
from trip_service.redis_client import close_redis, setup_redis
from trip_service.routers import driver_statement, health, removed_endpoints, trips
from platform_common import (
    instrument_app,
    setup_logging,
    setup_tracing,
    shutdown_tracing,
)

logger = logging.getLogger("trip_service")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    setup_logging(logging.INFO)
    validate_prod_settings(settings)

    # Initialise Core Platform Components
    setup_tracing(
        service_name="trip-service",
        service_version="0.1.0",
        environment=settings.environment,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
    )
    instrument_app(app)
    await setup_redis()

    broker = create_broker(settings.resolved_broker_type)
    app.state.broker = broker

    logger.info(
        "Trip Service starting on port %s (env=%s, broker=%s)",
        settings.service_port,
        settings.environment,
        settings.resolved_broker_type,
    )

    try:
        yield
    finally:
        await broker.close()
        await close_redis()
        await close_http_clients()
        shutdown_tracing()
        await engine.dispose()
        logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """Build the Trip Service ASGI application."""
    app = FastAPI(
        title="Trip Service",
        version="0.1.0",
        description="Trip lifecycle management microservice",
        lifespan=lifespan,
        docs_url=None if settings.environment == "prod" else "/docs",
    )

    # Standard Middleware
    app.add_middleware(PrometheusMiddleware)
    app.add_middleware(RequestIdMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "If-Match", "Idempotency-Key", "X-Idempotency-Key"],
        expose_headers=["ETag", "X-Correlation-ID"],
    )

    app.add_exception_handler(ProblemDetailError, problem_detail_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]

    app.include_router(health.router)
    app.include_router(removed_endpoints.router)
    app.include_router(trips.router)
    app.include_router(driver_statement.router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "trip_service.main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=settings.environment == "dev",
    )
