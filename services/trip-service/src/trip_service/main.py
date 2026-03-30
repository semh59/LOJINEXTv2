"""Trip Service FastAPI application entry point."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

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
from trip_service.observability import setup_logging
from trip_service.routers import driver_statement, health, removed_endpoints, trips

logger = logging.getLogger("trip_service")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    setup_logging()
    validate_prod_settings(settings)

    broker = create_broker(settings.resolved_broker_type)
    app.state.broker = broker
    logger.info("API startup complete; dedicated workers are expected to run separately")

    try:
        yield
    finally:
        await broker.close()
        await close_http_clients()
        await engine.dispose()
        logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """Build the Trip Service ASGI application."""
    app = FastAPI(
        title="Trip Service",
        version="0.1.0",
        description="Trip lifecycle management microservice",
        lifespan=lifespan,
    )

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(PrometheusMiddleware)

    app.add_exception_handler(ProblemDetailError, problem_detail_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]

    app.include_router(health.router)
    app.include_router(removed_endpoints.router)
    app.include_router(trips.router)
    app.include_router(driver_statement.router)
    return app


app = create_app()


if __name__ == "__main__":
    from trip_service.entrypoints.api import main

    main()
