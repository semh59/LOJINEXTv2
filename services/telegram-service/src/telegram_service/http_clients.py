import logging
import uuid

import httpx
from redis.asyncio import Redis

from platform_common.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from telegram_service.config import settings

logger = logging.getLogger(__name__)


class HttpClientManager:
    """Manages shared httpx.AsyncClient pools and circuit breakers."""

    def __init__(self):
        self.client: httpx.AsyncClient | None = None
        self.redis: Redis | None = None

        # Circuit Breakers
        self.trip_cb = CircuitBreaker(CircuitBreakerConfig(name="trip-service"))
        self.fleet_cb = CircuitBreaker(CircuitBreakerConfig(name="fleet-service"))
        self.driver_cb = CircuitBreaker(CircuitBreakerConfig(name="driver-service"))

    async def start(self):
        if self.client is None:
            self.client = httpx.AsyncClient(
                timeout=10.0,
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )

            if settings.redis_url:
                try:
                    self.redis = Redis.from_url(settings.redis_url, decode_responses=True)
                    await self.redis.ping()
                except Exception:
                    logger.warning("Failed to connect to Redis for circuit breakers, falling back to local state")
                    self.redis = None

            await self.trip_cb.init(self.redis)
            await self.fleet_cb.init(self.redis)
            await self.driver_cb.init(self.redis)

            logger.info("Shared HTTP client pool and circuit breakers started")

    async def stop(self):
        if self.client:
            await self.client.aclose()
            self.client = None
        if self.redis:
            await self.redis.close()
            self.redis = None
        logger.info("Shared HTTP client pool stopped")

    def get_client(self) -> httpx.AsyncClient:
        if self.client is None:
            raise RuntimeError("HttpClientManager not started. Call start() in lifespan.")
        return self.client

    async def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Execute request via the appropriate circuit breaker."""
        cb = self._get_breaker_for_url(url)
        client = self.get_client()

        if cb:
            return await cb.call(client.request, method, url, **kwargs)
        return await client.request(method, url, **kwargs)

    def _get_breaker_for_url(self, url: str) -> CircuitBreaker | None:
        if settings.trip_service_url in url:
            return self.trip_cb
        if settings.fleet_service_url in url:
            return self.fleet_cb
        if settings.driver_service_url in url:
            return self.driver_cb
        return None


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
