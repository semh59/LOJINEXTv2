"""Console-script entrypoint for identity-service API."""

from identity_service.config import settings


def main() -> None:
    """Start the identity-service ASGI server."""
    import uvicorn

    uvicorn.run(
        "identity_service.main:app",
        host="0.0.0.0",
        port=settings.service_port,
    )
