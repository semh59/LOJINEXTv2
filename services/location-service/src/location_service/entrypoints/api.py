"""CLI entrypoint for the location-service API process."""

from __future__ import annotations

import uvicorn

from location_service.config import settings


def main() -> None:
    """Run the FastAPI API process."""
    uvicorn.run(
        "location_service.main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=False,
    )
