"""Identity Service FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from identity_service.config import settings, validate_prod_settings
from identity_service.database import engine
from identity_service.routers.admin import router as admin_router
from identity_service.routers.auth import router as auth_router
from identity_service.routers.health import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup/shutdown hooks."""
    del app
    validate_prod_settings(settings)
    yield
    await engine.dispose()


app = FastAPI(
    title="Identity Service",
    version="0.1.0",
    description="Central auth, service-token issuance, and JWKS for LOJINEXT",
    lifespan=lifespan,
)

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
