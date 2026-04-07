"""Dedicated worker entrypoint for Fleet Service (outbox relay + heartbeat + cleanup)."""

from __future__ import annotations

import asyncio
import logging

from fleet_service.broker import create_broker
from fleet_service.config import settings
from fleet_service.database import async_session_factory, engine
from fleet_service.observability import setup_logging
from fleet_service.timestamps import utc_now_naive
from fleet_service.worker_heartbeats import record_worker_heartbeat
from fleet_service.workers.outbox_relay import run_outbox_relay

logger = logging.getLogger("fleet_service.entrypoints.worker")


async def _heartbeat_loop() -> None:
    """Periodically record a heartbeat for the worker process."""
    while True:
        try:
            await record_worker_heartbeat("fleet-worker")
        except Exception as exc:
            logger.error("Heartbeat loop error: %s", exc)
        await asyncio.sleep(settings.heartbeat_interval_seconds)


async def _idempotency_cleanup_loop() -> None:
    """Periodically delete expired idempotency records."""
    from sqlalchemy import delete

    from fleet_service.models import FleetIdempotencyRecord

    while True:
        try:
            async with async_session_factory() as session:
                now = utc_now_naive()
                stmt = delete(FleetIdempotencyRecord).where(FleetIdempotencyRecord.expires_at_utc < now)
                result = await session.execute(stmt)
                count = getattr(result, "rowcount", 0)  # Type-safe access for rowcount
                await session.commit()
                if count > 0:
                    logger.info("Idempotency cleanup: deleted %d expired records", count)
        except Exception as exc:
            logger.error("Idempotency cleanup error: %s", exc)
        await asyncio.sleep(settings.idempotency_cleanup_interval_hours * 3600)


async def worker_main() -> None:
    """Start all background worker loops."""
    setup_logging(logging.INFO)
    logger.info("Fleet Service worker starting (env=%s)", settings.environment)

    broker = create_broker(settings.resolved_broker_type)

    try:
        await asyncio.gather(
            run_outbox_relay(broker),
            _heartbeat_loop(),
            _idempotency_cleanup_loop(),
        )
    except asyncio.CancelledError:
        logger.info("Worker process cancelled")
    except Exception:
        logger.exception("Worker process encountered an error")
    finally:
        await engine.dispose()
        logger.info("Worker shutdown complete")


def main() -> None:
    """Entry point for the worker process."""
    asyncio.run(worker_main())


if __name__ == "__main__":
    main()
