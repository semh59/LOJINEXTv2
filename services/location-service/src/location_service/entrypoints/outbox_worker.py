"""CLI entrypoint for the location-service outbox relay worker."""

from __future__ import annotations

import asyncio
import logging

from location_service.observability import setup_logging
from location_service.outbox_relay import run_outbox_relay

logger = logging.getLogger("location_service.entrypoints.outbox_worker")


def main() -> None:
    """Run the dedicated outbox relay loop."""
    setup_logging()
    logger.info("Starting Location Outbox Worker")
    try:
        asyncio.run(run_outbox_relay())
    except KeyboardInterrupt:
        logger.info("Outbox worker stopped by user")
    except Exception as exc:
        logger.critical("Outbox worker failed: %s", exc, exc_info=True)


if __name__ == "__main__":
    main()
