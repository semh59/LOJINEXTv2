"""CLI entrypoint for the trip-service outbox relay worker."""

from __future__ import annotations

import asyncio
import logging
import signal

from trip_service.broker import create_broker
from trip_service.config import settings, validate_prod_settings
from trip_service.observability import setup_logging
from trip_service.redis_client import setup_redis, close_redis
from trip_service.workers.outbox_relay import run_outbox_relay
from platform_common import setup_tracing, shutdown_tracing

logger = logging.getLogger("trip_service.entrypoints.outbox_worker")


async def _run_worker(shutdown_event: asyncio.Event) -> None:
    broker = create_broker(settings.resolved_broker_type)
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, shutdown_event.set)

        await run_outbox_relay(broker, shutdown_event=shutdown_event)
    finally:
        await broker.close()
        await close_redis()
        shutdown_tracing()


def main() -> None:
    """Run the dedicated outbox relay loop with graceful shutdown support."""
    setup_logging()
    validate_prod_settings(settings)

    setup_tracing(
        service_name="trip-service-worker",
        service_version="0.1.0",
        environment=settings.environment,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
    )

    # We initialization Redis here if the worker needs it (e.g. for heartbeats or enrichment fallback)
    # Trip outbox relay by default doesn't need Redis but consistency is key
    asyncio.run(setup_redis())

    logger.info("Starting Trip Outbox Worker")

    shutdown_event = asyncio.Event()
    try:
        asyncio.run(_run_worker(shutdown_event))
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Outbox worker stopped")
    except Exception as exc:
        logger.critical("Outbox worker failed: %s", exc, exc_info=True)


if __name__ == "__main__":
    main()
