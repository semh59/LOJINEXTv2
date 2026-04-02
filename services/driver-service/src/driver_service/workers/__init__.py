"""Driver Service workers entry point."""

from __future__ import annotations

import asyncio
import logging

from driver_service.broker import EventBroker
from driver_service.workers.import_worker import run_import_worker
from driver_service.workers.outbox_relay import run_outbox_relay

logger = logging.getLogger("driver_service.workers")


async def start_all_workers(broker: EventBroker) -> None:
    """Start all background workers for the Driver Service."""
    logger.info("Starting Driver Service workers...")

    await asyncio.gather(
        run_outbox_relay(broker),
        run_import_worker(),
    )
