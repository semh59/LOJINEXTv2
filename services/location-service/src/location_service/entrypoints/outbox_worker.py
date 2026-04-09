"""CLI entrypoint for the location-service outbox relay worker."""

from __future__ import annotations

import asyncio
import logging
import signal

from location_service.observability import setup_logging
from location_service.outbox_relay import run_outbox_relay

logger = logging.getLogger("location_service.entrypoints.outbox_worker")


async def _run_worker(shutdown_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown_event.set)

    await run_outbox_relay(shutdown_event=shutdown_event)


def main() -> None:
    """Run the dedicated outbox relay loop with graceful shutdown support."""
    setup_logging()
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
