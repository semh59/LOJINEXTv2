"""Dedicated outbox relay process entrypoint."""

from __future__ import annotations

import asyncio
import logging
import signal

from trip_service.broker import create_broker
from trip_service.config import settings
from trip_service.entrypoints._runtime import configure_process, shutdown_process
from trip_service.workers.outbox_relay import run_outbox_relay

logger = logging.getLogger("trip_service.entrypoints.outbox_worker")


async def _run() -> None:
    configure_process()
    broker = create_broker(settings.resolved_broker_type)
    shutdown_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown_event.set)

    logger.info("Starting dedicated outbox relay process with broker %s", type(broker).__name__)
    try:
        await run_outbox_relay(broker, shutdown_event=shutdown_event)
    finally:
        await shutdown_process()
        logger.info("Outbox relay process stopped")


def main() -> None:
    """Run the Trip Service outbox relay worker."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
