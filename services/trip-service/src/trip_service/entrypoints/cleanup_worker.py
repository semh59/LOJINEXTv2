"""Dedicated cleanup worker process entrypoint."""

from __future__ import annotations

import asyncio
import logging
import signal

from trip_service.entrypoints._runtime import configure_process, shutdown_process
from trip_service.observability import run_cleanup_loop

logger = logging.getLogger("trip_service.entrypoints.cleanup_worker")


async def _run() -> None:
    configure_process()
    shutdown_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    try:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, shutdown_event.set)
    except NotImplementedError:
        logger.warning("Signal handlers not supported on this platform. Graceful shutdown may not work.")

    logger.info("Starting dedicated cleanup worker process")
    try:
        await run_cleanup_loop(shutdown_event=shutdown_event)
    finally:
        await shutdown_process()
        logger.info("Cleanup worker process stopped")


def main() -> None:
    """Run the Trip Service cleanup worker."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
