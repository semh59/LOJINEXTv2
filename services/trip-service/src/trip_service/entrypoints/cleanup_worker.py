"""Dedicated cleanup worker process entrypoint."""

from __future__ import annotations

import asyncio
import logging

from trip_service.entrypoints._runtime import configure_process, shutdown_process
from trip_service.observability import run_cleanup_loop

logger = logging.getLogger("trip_service.entrypoints.cleanup_worker")


async def _run() -> None:
    configure_process()
    logger.info("Starting dedicated cleanup worker process")
    try:
        await run_cleanup_loop()
    finally:
        await shutdown_process()
        logger.info("Cleanup worker process stopped")


def main() -> None:
    """Run the Trip Service cleanup worker."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
