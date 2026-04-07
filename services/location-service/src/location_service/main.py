"""Location Service FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError

from location_service.auth import trip_service_auth_dependency, user_auth_dependency
from location_service.broker import create_broker
from location_service.config import settings, validate_prod_settings
from location_service.database import engine
from location_service.errors import (
    ProblemDetailError,
    problem_detail_handler,
    unexpected_exception_handler,
    validation_exception_handler,
)
from location_service.middleware import PrometheusMiddleware, RequestIdMiddleware
from location_service.observability import setup_logging
from location_service.routers import (
    approval,
    bulk_refresh,
    health,
    internal_routes,
    pairs,
    points,
    processing,
    removed_endpoints,
    routes_public,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan events."""
    setup_logging()
    validate_prod_settings(settings)
    # create_broker() handles its own resolution from settings
    app.state.broker = create_broker()
    yield
    # EventBroker interface uses close(), not stop()
    await app.state.broker.close()
    await engine.dispose()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    docs_enabled = settings.environment != "prod"
    app = FastAPI(
        title=f"Location Service ({settings.environment})",
        description="Authoritative source for locations, routes, and segment geometry.",
        version="0.7.0",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(PrometheusMiddleware)
    app.add_exception_handler(ProblemDetailError, problem_detail_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unexpected_exception_handler)
    app.include_router(health.router)
    public_dependencies = [Depends(user_auth_dependency)]
    app.include_router(points.router, dependencies=public_dependencies)
    app.include_router(pairs.router, dependencies=public_dependencies)
    app.include_router(processing.router, dependencies=public_dependencies)
    app.include_router(processing.public_router, dependencies=public_dependencies)
    app.include_router(approval.router, dependencies=public_dependencies)
    app.include_router(bulk_refresh.router, dependencies=public_dependencies)
    app.include_router(routes_public.router, dependencies=public_dependencies)
    app.include_router(removed_endpoints.router, dependencies=public_dependencies)
    app.include_router(internal_routes.router, dependencies=[Depends(trip_service_auth_dependency)])
    return app


app = create_app()
