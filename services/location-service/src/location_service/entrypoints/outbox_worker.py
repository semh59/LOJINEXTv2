"""CLI entrypoint for the location-service outbox relay worker."""

from __future__ import annotations

import asyncio
import logging
import signal

from platform_common import setup_tracing, shutdown_tracing

from location_service.broker import create_broker
from location_service.config import settings, validate_prod_settings
from location_service.observability import setup_logging
from location_service.workers.outbox_relay import run_outbox_relay

logger = logging.getLogger("location_service.entrypoints.outbox_worker")


async def _run_worker(shutdown_event: asyncio.Event) -> None:
    broker = create_broker()
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, shutdown_event.set)

        await run_outbox_relay(broker, shutdown_event=shutdown_event)
    finally:
        await broker.close()
        from location_service.database import engine

        await engine.dispose()
        shutdown_tracing()


def main() -> None:
    """Run the dedicated outbox relay loop with graceful shutdown support."""
    setup_logging()
    validate_prod_settings(settings)

    setup_tracing(
        service_name="location-service-worker",
        service_version="0.1.0",
        environment=settings.environment,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
    )

    logger.info("Starting Location Outbox Worker")

    shutdown_event = asyncio.Event()
    try:
        asyncio.run(_run_worker(shutdown_event))
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Outbox worker stopped")
    except Exception as exc:
        logger.critical("Outbox worker failed: %s", exc, exc_info=True)


if __name__ == "__main__":
    main()
