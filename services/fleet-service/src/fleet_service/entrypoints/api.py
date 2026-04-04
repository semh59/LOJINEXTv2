"""Dedicated API entrypoint for Fleet Service."""

from __future__ import annotations

import uvicorn

from fleet_service.config import settings


def main() -> None:
    """Run the Fleet Service API process."""
    uvicorn.run(
        "fleet_service.main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=settings.environment == "dev",
    )


if __name__ == "__main__":
    main()
