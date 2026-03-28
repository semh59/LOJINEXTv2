from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from location_service.config import settings
from location_service.database import engine
from location_service.errors import ProblemDetailError, problem_detail_handler
from location_service.middleware import RequestIdMiddleware
from location_service.routers import (
    approval,
    bulk_refresh,
    health,
    import_export,
    internal_routes,
    pairs,
    points,
    processing,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan events.

    Handles startup (e.g., stuck run recovery if implemented later) and shutdown
    cleanup of database connections.
    """
    # Startup tasks go here.

    yield

    # Shutdown logic
    await engine.dispose()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title=f"Location Service ({settings.env_name})",
        description="Authoritative source for locations, routes, and segment geometry.",
        version="0.7.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Global middleware (pure ASGI)
    app.add_middleware(RequestIdMiddleware)

    # Global exception handlers
    app.add_exception_handler(ProblemDetailError, problem_detail_handler)

    # Routers
    app.include_router(health.router)
    app.include_router(points.router)
    app.include_router(pairs.router)
    app.include_router(processing.router)
    app.include_router(approval.router)
    app.include_router(bulk_refresh.router)
    app.include_router(import_export.router)
    app.include_router(internal_routes.router)

    return app


app = create_app()
