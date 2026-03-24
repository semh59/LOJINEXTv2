"""Trip Service — FastAPI application entry point.

V8 Section 2: service-name = trip-service, port = 8101.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from trip_service.broker import create_broker
from trip_service.config import settings
from trip_service.database import engine
from trip_service.errors import ProblemDetailError, problem_detail_handler
from trip_service.middleware import RequestIdMiddleware
from trip_service.observability import run_cleanup_loop, setup_logging
from trip_service.routers import health, import_export, trips
from trip_service.workers.enrichment_worker import run_enrichment_worker
from trip_service.workers.outbox_relay import run_outbox_relay

logger = logging.getLogger("trip_service")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    # Configure structured logging
    setup_logging()

    # Startup: launch background workers
    broker = create_broker("log")  # Injectable: swap to "kafka" / "rabbitmq" in prod
    worker_tasks: list[asyncio.Task[None]] = [
        asyncio.create_task(run_enrichment_worker(), name="enrichment-worker"),
        asyncio.create_task(run_outbox_relay(broker), name="outbox-relay"),
        asyncio.create_task(run_cleanup_loop(), name="cleanup"),
    ]
    logger.info("Background workers started: enrichment-worker, outbox-relay, cleanup")

    yield

    # Shutdown: cancel workers, dispose engine
    for task in worker_tasks:
        task.cancel()
    await asyncio.gather(*worker_tasks, return_exceptions=True)
    await engine.dispose()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Trip Service",
    version="0.1.0",
    description="Trip lifecycle management microservice (V8 spec)",
    lifespan=lifespan,
)

# --- Middleware ---
app.add_middleware(RequestIdMiddleware)

# --- Exception Handlers ---
app.add_exception_handler(ProblemDetailError, problem_detail_handler)  # type: ignore[arg-type]

# --- Routers ---
app.include_router(health.router)
app.include_router(trips.router)
app.include_router(import_export.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "trip_service.main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=True,
    )
