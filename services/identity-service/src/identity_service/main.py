"""Identity Service FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from identity_service.config import settings, validate_prod_settings
from identity_service.database import engine, async_session_factory
from identity_service.middleware import PrometheusMiddleware, RequestIdMiddleware
from identity_service.routers.admin import router as admin_router
from identity_service.routers.auth import router as auth_router
from identity_service.routers.health import router as health_router
from identity_service.token_service import (
    ensure_active_signing_key,
    seed_bootstrap_state,
)

import logging
from sqlalchemy import text

logger = logging.getLogger("identity_service")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup/shutdown hooks."""
    del app
    validate_prod_settings(settings)

    # Bootstrap state and signing keys once on startup
    async with async_session_factory() as session:
        try:
            # 78216 is an arbitrary 64-bit integer for the lock key
            await session.execute(text("SELECT pg_advisory_xact_lock(78216)"))
            logger.info("Acquired bootstrap advisory lock")

            await seed_bootstrap_state(session)
            await ensure_active_signing_key(session)
            await session.commit()
            logger.info("Bootstrap complete")
        except Exception as exc:
            await session.rollback()
            logger.error(f"Failed to bootstrap Identity Service: {exc}")
            # In production, we want to fail fast if we can't bootstrap
            raise RuntimeError(f"Failed to bootstrap Identity Service: {exc}") from exc

    yield
    await engine.dispose()


app = FastAPI(
    title="Identity Service",
    version="0.1.0",
    description="Central auth, service-token issuance, and JWKS for LOJINEXT",
    lifespan=lifespan,
)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(PrometheusMiddleware)

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
