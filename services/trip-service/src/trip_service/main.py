"""Trip Service FastAPI application entry point."""

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from trip_service.broker import create_broker
from trip_service.config import settings
from trip_service.database import engine
from trip_service.errors import (
    ProblemDetailError,
    problem_detail_handler,
    validation_exception_handler,
)
from trip_service.middleware import RequestIdMiddleware
from trip_service.observability import run_cleanup_loop, setup_logging
from trip_service.routers import driver_statement, health, removed_endpoints, trips
from trip_service.workers.enrichment_worker import run_enrichment_worker
from trip_service.workers.outbox_relay import run_outbox_relay

logger = logging.getLogger("trip_service")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    setup_logging()

    broker = create_broker(settings.resolved_broker_type)
    app.state.broker = broker
    worker_tasks: list[asyncio.Task[None]] = [
        asyncio.create_task(run_enrichment_worker(), name="enrichment-worker"),
        asyncio.create_task(run_outbox_relay(broker), name="outbox-relay"),
        asyncio.create_task(run_cleanup_loop(), name="cleanup"),
    ]
    logger.info("Background workers started: enrichment-worker, outbox-relay, cleanup")

    yield

    for task in worker_tasks:
        task.cancel()
    await asyncio.gather(*worker_tasks, return_exceptions=True)
    await engine.dispose()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Trip Service",
    version="0.1.0",
    description="Trip lifecycle management microservice",
    lifespan=lifespan,
)

app.add_middleware(RequestIdMiddleware)

app.add_exception_handler(ProblemDetailError, problem_detail_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]

app.include_router(health.router)
app.include_router(removed_endpoints.router)
app.include_router(trips.router)
app.include_router(driver_statement.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "trip_service.main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=True,
    )
