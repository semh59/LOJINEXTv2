"""Dedicated outbox relay process entrypoint."""

from __future__ import annotations

import asyncio
import logging

from trip_service.broker import create_broker
from trip_service.config import settings
from trip_service.entrypoints._runtime import configure_process, shutdown_process
from trip_service.workers.outbox_relay import run_outbox_relay

logger = logging.getLogger("trip_service.entrypoints.outbox_worker")


async def _run() -> None:
    configure_process()
    broker = create_broker(settings.resolved_broker_type)
    logger.info("Starting dedicated outbox relay process with broker %s", type(broker).__name__)
    try:
        await run_outbox_relay(broker)
    finally:
        await shutdown_process()
        logger.info("Outbox relay process stopped")


def main() -> None:
    """Run the Trip Service outbox relay worker."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
