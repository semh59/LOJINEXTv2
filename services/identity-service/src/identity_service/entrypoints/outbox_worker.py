"""Console-script entrypoint for the identity-service outbox worker."""

from __future__ import annotations

import asyncio
import signal

from identity_service.broker import create_broker
from identity_service.config import settings
from identity_service.workers.cleanup_worker import run_cleanup
from identity_service.workers.outbox_relay import run_outbox_relay


async def _run() -> None:
    from identity_service.config import validate_prod_settings
    from identity_service.observability import setup_logging
    from identity_service.redis_client import setup_redis
    from platform_common import setup_tracing, shutdown_tracing

    setup_logging("INFO")
    validate_prod_settings(settings)

    setup_tracing(
        service_name="identity-service-worker",
        service_version="0.1.0",
        environment=settings.environment,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
    )
    await setup_redis()

    broker = create_broker(settings.resolved_broker_backend)
    shutdown_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown_event.set)

    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(run_outbox_relay(broker, shutdown_event=shutdown_event))
            tg.create_task(run_cleanup(shutdown_event=shutdown_event))
    finally:
        await broker.close()
        from identity_service.database import engine
        from identity_service.redis_client import close_redis

        await engine.dispose()
        await close_redis()
        shutdown_tracing()


def main() -> None:
    """Start the identity-service outbox worker."""
    asyncio.run(_run())
