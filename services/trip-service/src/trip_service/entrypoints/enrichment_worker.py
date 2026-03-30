"""Dedicated enrichment worker process entrypoint."""

from __future__ import annotations

import asyncio
import logging

from trip_service.entrypoints._runtime import configure_process, shutdown_process
from trip_service.workers.enrichment_worker import run_enrichment_worker

logger = logging.getLogger("trip_service.entrypoints.enrichment_worker")


async def _run() -> None:
    configure_process()
    logger.info("Starting dedicated enrichment worker process")
    try:
        await run_enrichment_worker()
    finally:
        await shutdown_process()
        logger.info("Enrichment worker process stopped")


def main() -> None:
    """Run the Trip Service enrichment worker."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
