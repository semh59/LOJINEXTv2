"""Identity Service FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError

from identity_service.config import settings, validate_prod_settings
from identity_service.database import async_session_factory, engine
from identity_service.errors import (
    ProblemDetailError,
    problem_detail_handler,
    validation_exception_handler,
    internal_error,
)
from identity_service.middleware import (
    PrometheusMiddleware,
    RateLimitMiddleware,
    RequestIdMiddleware,
)
from identity_service.routers.admin import router as admin_router
from identity_service.routers.auth import router as auth_router
from identity_service.routers.health import router as health_router
from identity_service.token_service import (
    _executor,
    seed_bootstrap_state,
    validate_bootstrap_state,
)

import logging
from sqlalchemy import text

logger = logging.getLogger("identity_service")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup/shutdown hooks."""
    from platform_common import (
        setup_logging,
        setup_tracing,
        instrument_app,
        shutdown_tracing,
    )
    from identity_service.redis_client import setup_redis

    setup_logging(logging.INFO)
    validate_prod_settings(settings)

    # Initialise Core Platform Components
    setup_tracing(
        service_name="identity-service",
        service_version="0.1.0",
        environment=settings.environment,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
    )
    instrument_app(app)
    await setup_redis()

    async with async_session_factory() as session:
        try:
            if engine.dialect.name == "postgresql":
                await session.execute(text("SELECT pg_advisory_xact_lock(78216)"))
                logger.info("Acquired bootstrap advisory lock")

            await seed_bootstrap_state(session)
            await validate_bootstrap_state(session)
            await session.commit()
            logger.info("Bootstrap complete")
        except Exception as exc:
            await session.rollback()
            logger.error(f"Failed to bootstrap Identity Service: {exc}")
            raise RuntimeError(f"Failed to bootstrap Identity Service: {exc}") from exc

    yield

    from identity_service.redis_client import close_redis

    await close_redis()
    shutdown_tracing()
    await engine.dispose()
    _executor.shutdown(wait=True)
    logger.info("Identity Service shutdown complete")


app = FastAPI(
    title="Identity Service",
    version="0.1.0",
    description="Central auth, service-token issuance, and JWKS for LOJINEXT",
    lifespan=lifespan,
    docs_url=None if settings.environment == "prod" else "/docs",
    redoc_url=None if settings.environment == "prod" else "/redoc",
)

# Middleware stack (outermost first — Starlette applies in reverse registration order)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(PrometheusMiddleware)

# RateLimitMiddleware is a raw ASGI middleware (not BaseHTTPMiddleware),
# so it must be added via add_middleware with the class, not an instance.
# FastAPI will wrap it correctly around the app.
app.add_middleware(RateLimitMiddleware)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    problem = ProblemDetailError(
        status=exc.status_code,
        code=f"HTTP_{exc.status_code}",
        title="HTTP Exception",
        detail=str(exc.detail),
    )
    return await problem_detail_handler(request, problem)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler_route(request: Request, exc: RequestValidationError):
    return await validation_exception_handler(request, exc)


@app.exception_handler(Exception)
async def unexpected_exception_handler(request: Request, exc: Exception):
    logger.exception("Unexpected error occurred: %s", exc)
    return await problem_detail_handler(request, internal_error())


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(admin_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "identity_service.main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=True,
    )
