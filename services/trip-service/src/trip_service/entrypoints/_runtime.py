"""Shared process bootstrap helpers for Trip Service entrypoints."""

from __future__ import annotations

import logging

from trip_service.config import settings, validate_prod_settings
from trip_service.database import engine
from trip_service.http_clients import close_http_clients
from trip_service.observability import setup_logging

logger = logging.getLogger("trip_service.runtime")


def configure_process() -> None:
    """Apply common logging and production validation for a runtime process."""
    setup_logging()
    validate_prod_settings(settings)


async def shutdown_process() -> None:
    """Release shared process resources on worker shutdown."""
    await close_http_clients()
    await engine.dispose()
