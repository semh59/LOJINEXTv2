"""Dedicated API entrypoint for Trip Service."""

from __future__ import annotations

import uvicorn

from trip_service.config import settings
from trip_service.main import create_app

app = create_app()


def main() -> None:
    """Run the Trip Service API process."""
    uvicorn.run(
        "trip_service.entrypoints.api:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=settings.environment == "dev",
    )


if __name__ == "__main__":
    main()
