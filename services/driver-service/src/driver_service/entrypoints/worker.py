"""Dedicated worker entrypoint for Driver Service."""

from __future__ import annotations

import asyncio
import logging

from driver_service.broker import create_broker
from driver_service.config import settings
from driver_service.database import engine
from driver_service.observability import setup_structured_logging
from driver_service.workers import start_all_workers

logger = logging.getLogger("driver_service.entrypoints.worker")


async def worker_main() -> None:
    setup_structured_logging(logging.INFO)
    logger.info("Driver Service worker starting (env=%s)", settings.environment)

    broker = create_broker(settings.resolved_broker_type)

    try:
        await start_all_workers(broker)
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
