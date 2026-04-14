"""Console-script entrypoint for auth-service API."""

from auth_service.config import settings


def main() -> None:
    """Start the auth-service ASGI server."""
    import uvicorn

    uvicorn.run(
        "auth_service.main:app",
        host="0.0.0.0",
        port=settings.service_port,
    )
