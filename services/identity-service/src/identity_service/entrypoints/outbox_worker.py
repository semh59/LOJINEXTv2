"""Console-script entrypoint for the identity-service outbox worker."""

from __future__ import annotations

import asyncio

from identity_service.broker import create_broker
from identity_service.config import settings
from identity_service.workers.outbox_relay import run_outbox_relay


async def _run() -> None:
    broker = create_broker(settings.resolved_broker_backend)
    try:
        await run_outbox_relay(broker)
    finally:
        await broker.close()


def main() -> None:
    """Start the identity-service outbox worker."""
    asyncio.run(_run())
