"""Dedicated API entrypoint for Driver Service."""

from __future__ import annotations

import uvicorn

from driver_service.config import settings


def main() -> None:
    """Run the Driver Service API process."""
    uvicorn.run(
        "driver_service.main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=settings.environment == "dev",
    )


if __name__ == "__main__":
    main()
