"""Application configuration via environment variables."""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Telegram Service configuration loaded from environment variables."""

    service_name: str = "telegram-service"
    service_version: str = "0.1.0"
    service_port: int = 8106
    environment: Literal["dev", "test", "prod"] = "dev"

    # Telegram bot
    bot_token: str = ""
    webhook_url: str = ""  # If set, use webhook mode; otherwise polling
    webhook_secret: str = ""  # Optional secret token for webhook verification

    # FSM storage — Redis URL enables persistent FSM state across restarts
    redis_url: str = ""  # If empty, MemoryStorage is used (dev/test)

    # Upstream services
    trip_service_url: str = "http://localhost:8101"
    fleet_service_url: str = "http://localhost:8102"
    driver_service_url: str = "http://localhost:8104"
    dependency_timeout_seconds: float = 10.0

    # Outbound auth (service-to-service JWT issuance)
    auth_jwt_algorithm: str = "RS256"
    auth_issuer: str = "lojinext-platform"
    auth_audience: str = "lojinext-platform"
    auth_public_key: str = ""
    auth_private_key: str = ""
    auth_jwks_url: str = ""
    auth_jwks_cache_ttl_seconds: int = 300
    auth_service_token_url: str = ""
    auth_service_client_id: str = "telegram-service"
    auth_service_client_secret: str = ""

    # Business rules
    max_date_range_days: int = 31  # Mirrors trip-service limit
    driver_cache_ttl_seconds: int = 300  # In-memory driver lookup cache TTL
    ocr_confidence_threshold: float = 0.5  # Below → fallback ingest
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"

    model_config = {"env_prefix": "TELEGRAM_", "env_file": ".env", "extra": "ignore"}


settings = Settings()


def validate_prod_settings(current: Settings) -> None:
    """Fail fast when production settings are insecure or missing."""
    if current.environment != "prod":
        return

    errors: list[str] = []
    if not current.bot_token:
        errors.append("TELEGRAM_BOT_TOKEN must be set in prod.")
    if not current.webhook_url:
        errors.append("TELEGRAM_WEBHOOK_URL must be set in prod (polling not allowed).")
    if current.auth_jwt_algorithm.upper() != "RS256":
        errors.append("TELEGRAM_AUTH_JWT_ALGORITHM must be RS256 in prod.")
    if not current.auth_service_token_url:
        errors.append("TELEGRAM_AUTH_SERVICE_TOKEN_URL must be set in prod.")
    if not current.auth_service_client_secret:
        errors.append("TELEGRAM_AUTH_SERVICE_CLIENT_SECRET must be set in prod.")
    if not current.redis_url:
        errors.append("TELEGRAM_REDIS_URL must be set in prod for persistent FSM state.")

    if errors:
        raise ValueError("Production settings invalid: " + " ".join(errors))
