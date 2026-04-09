"""Dedicated worker entrypoint for Driver Service."""

from __future__ import annotations

import asyncio
import logging
import signal

from driver_service.broker import create_broker
from driver_service.config import settings, validate_prod_settings
from driver_service.database import engine
from driver_service.observability import setup_logging
from driver_service.workers import start_all_workers

logger = logging.getLogger("driver_service.entrypoints.worker")


async def worker_main() -> None:
    setup_logging(logging.INFO)
    validate_prod_settings(settings)
    logger.info("Driver Service worker starting (env=%s)", settings.environment)

    broker = create_broker(settings.resolved_broker_type)
    shutdown_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown_event.set)

    try:
        await start_all_workers(broker, shutdown_event=shutdown_event)
    except asyncio.CancelledError:
        logger.info("Worker process cancelled")
    except Exception:
        logger.exception("Worker process encountered an error")
    finally:
        await broker.close()
        await engine.dispose()
        logger.info("Worker shutdown complete")


def main() -> None:
    asyncio.run(worker_main())


if __name__ == "__main__":
    main()
