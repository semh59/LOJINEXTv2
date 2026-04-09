"""CLI entrypoint for the location-service processing worker."""

from __future__ import annotations

import asyncio
import logging
import signal

from location_service.observability import setup_logging
from location_service.processing.worker import run_processing_worker

logger = logging.getLogger("location_service.entrypoints.processing_worker")


async def _run_worker(shutdown_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown_event.set)

    await run_processing_worker(shutdown_event=shutdown_event)


def main() -> None:
    """Run the dedicated processing worker loop with graceful shutdown support."""
    setup_logging()
    logger.info("Starting Location Processing Worker")

    shutdown_event = asyncio.Event()
    try:
        asyncio.run(_run_worker(shutdown_event))
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Processing worker stopped")
    except Exception as exc:
        logger.critical("Processing worker failed: %s", exc, exc_info=True)
