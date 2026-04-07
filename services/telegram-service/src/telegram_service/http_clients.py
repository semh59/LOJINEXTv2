"""Shared HTTP client management for telegram-service."""

from __future__ import annotations

import logging
import uuid
import httpx

logger = logging.getLogger(__name__)


class HttpClientManager:
    """Manages shared httpx.AsyncClient pools for production readiness."""

    def __init__(self):
        self.client: httpx.AsyncClient | None = None

    async def start(self):
        if self.client is None:
            self.client = httpx.AsyncClient(
                timeout=10.0,
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )
            logger.info("Shared HTTP client pool started (max_connections=100)")

    async def stop(self):
        if self.client:
            await self.client.aclose()
            self.client = None
            logger.info("Shared HTTP client pool stopped")

    def get_client(self) -> httpx.AsyncClient:
        if self.client is None:
            raise RuntimeError("HttpClientManager not started. Call start() in lifespan.")
        return self.client


# Global instance
http_manager = HttpClientManager()


async def get_headers() -> dict[str, str]:
    """Helper to generate standard service-to-service headers."""
    from telegram_service.auth import issue_service_token
    from telegram_service.observability import get_correlation_id

    token = await issue_service_token()
    cid = get_correlation_id() or str(uuid.uuid4())

    return {
        "Authorization": f"Bearer {token}",
        "X-Correlation-ID": cid,
        "Content-Type": "application/json",
    }
