"""CLI entrypoint for the location-service processing worker."""

from __future__ import annotations

import asyncio

from location_service.observability import setup_logging
from location_service.processing.worker import run_processing_worker


def main() -> None:
    """Run the dedicated processing worker loop."""
    setup_logging()
    asyncio.run(run_processing_worker())
