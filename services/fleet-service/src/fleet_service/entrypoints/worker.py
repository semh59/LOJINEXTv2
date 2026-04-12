"""Dedicated worker entrypoint for Fleet Service (outbox relay + heartbeat + cleanup)."""

from __future__ import annotations

import asyncio
import logging
import signal

from fleet_service.broker import create_broker
from fleet_service.config import settings
from fleet_service.database import async_session_factory, engine
from fleet_service.observability import setup_logging
from fleet_service.timestamps import utc_now_aware
from fleet_service.worker_heartbeats import record_worker_heartbeat
from fleet_service.workers.outbox_relay import run_outbox_relay

logger = logging.getLogger("fleet_service.entrypoints.worker")


async def _heartbeat_loop(shutdown_event: asyncio.Event | None = None) -> None:
    """Periodically record a heartbeat for the worker process."""
    while True:
        if shutdown_event and shutdown_event.is_set():
            return

        try:
            await record_worker_heartbeat("fleet-worker")
        except Exception as exc:
            logger.error("Heartbeat loop error: %s", exc)
        await asyncio.sleep(settings.heartbeat_interval_seconds)


async def _idempotency_cleanup_loop(shutdown_event: asyncio.Event | None = None) -> None:
    """Periodically delete expired idempotency records."""
    from sqlalchemy import delete

    from fleet_service.models import FleetIdempotencyRecord

    while True:
        if shutdown_event and shutdown_event.is_set():
            return

        try:
            async with async_session_factory() as session:
                now = utc_now_aware()
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
    """Start all background worker loops with graceful shutdown support."""
    setup_logging(logging.INFO)

    from fleet_service.redis_client import setup_redis
    from platform_common import setup_tracing, shutdown_tracing

    setup_tracing(
        service_name="fleet-service-worker",
        service_version="0.1.0",
        environment=settings.environment,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
    )
    await setup_redis()

    logger.info("Fleet Service worker starting (env=%s)", settings.environment)

    broker = create_broker(settings.resolved_broker_type)
    shutdown_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown_event.set)

    try:
        await asyncio.gather(
            run_outbox_relay(broker, shutdown_event=shutdown_event),
            _heartbeat_loop(shutdown_event=shutdown_event),
            _idempotency_cleanup_loop(shutdown_event=shutdown_event),
        )
    except asyncio.CancelledError:
        logger.info("Worker process cancelled")
    except Exception:
        logger.exception("Worker process encountered an error")
    finally:
        await broker.close()
        from fleet_service.redis_client import close_redis

        await close_redis()
        shutdown_tracing()
        await engine.dispose()
        logger.info("Worker shutdown complete")


def main() -> None:
    """Entry point for the worker process."""
    asyncio.run(worker_main())


if __name__ == "__main__":
    main()
