"""Application configuration via environment variables."""

import os
from typing import Literal

from pydantic_settings import BaseSettings

DEFAULT_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/location_service"
DEFAULT_AUTH_JWT_SECRET = "location-service-dev-secret-please-change-me-32b"
DEFAULT_MAPBOX_DIRECTIONS_BASE_URL = "https://api.mapbox.com/directions/v5"
DEFAULT_MAPBOX_RASTER_BASE_URL = "https://api.mapbox.com/v4"
DEFAULT_ORS_BASE_URL = "https://api.openrouteservice.org/v2/directions/driving-hgv"


class Settings(BaseSettings):
    """Location Service configuration loaded from environment variables."""

    service_name: str = "location-service"
    service_port: int = 8103
    environment: Literal["dev", "test", "prod"] = "dev"

    database_url: str = DEFAULT_DATABASE_URL

    api_version: str = "v1"
    profile_default: str = "TIR"

    auth_jwt_secret: str = DEFAULT_AUTH_JWT_SECRET
    auth_jwt_algorithm: str = "HS256"
    auth_issuer: str = ""
    auth_audience: str = ""
    auth_public_key: str = ""
    auth_private_key: str = ""
    auth_jwks_url: str = ""
    auth_jwks_cache_ttl_seconds: int = 300
    auth_service_token_url: str = ""
    auth_service_client_id: str = "location-service"
    auth_service_client_secret: str = ""

    mapbox_api_key: str = ""
    mapbox_directions_base_url: str = DEFAULT_MAPBOX_DIRECTIONS_BASE_URL
    mapbox_raster_base_url: str = DEFAULT_MAPBOX_RASTER_BASE_URL

    ors_api_key: str = ""
    ors_base_url: str = DEFAULT_ORS_BASE_URL
    enable_ors_validation: bool = True

    provider_timeout_ms: int = 4000
    distance_delta_fail_pct: float = 15.0
    duration_delta_warning_pct: float = 10.0
    duration_delta_fail_pct: float = 20.0
    endpoint_parity_tolerance_m: float = 25.0
    known_speed_limit_ratio_warning: float = 0.85
    known_speed_limit_ratio_fail: float = 0.50

    hard_delete_grace_period_days: int = 30
    idempotency_ttl_hours: int = 24
    monthly_refresh_cron: str = ""
    enable_bulk_refresh: bool = True
    run_stuck_sla_minutes: int = 30
    outbox_poll_interval_seconds: int = 5
    outbox_publish_batch_size: int = 50
    outbox_retry_max: int = 5
    kafka_topic: str = "location-events"
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_client_id: str = "location-service"

    @property
    def resolved_auth_jwt_secret(self) -> str:
        """Return the recovery-time shared secret if set, otherwise the local auth secret."""
        return os.getenv("PLATFORM_JWT_SECRET") or self.auth_jwt_secret

    @property
    def provider_timeout_seconds(self) -> float:
        """Return the provider timeout in seconds for HTTPX clients."""
        return max(self.provider_timeout_ms, 1) / 1000.0

    model_config = {"env_prefix": "LOCATION_", "env_file": ".env", "extra": "ignore"}


settings = Settings()


def validate_prod_settings(current: Settings) -> None:
    """Fail fast when production settings are insecure or incomplete."""
    if current.environment != "prod":
        return

    errors: list[str] = []
    if current.auth_jwt_algorithm.upper().startswith("HS") and (
        not current.resolved_auth_jwt_secret or current.resolved_auth_jwt_secret == DEFAULT_AUTH_JWT_SECRET
    ):
        errors.append("LOCATION_AUTH_JWT_SECRET must be set to a non-default value in prod.")
    if current.auth_jwt_algorithm.upper().startswith("RS"):
        if not current.auth_jwks_url and not current.auth_public_key:
            errors.append("LOCATION_AUTH_JWKS_URL or LOCATION_AUTH_PUBLIC_KEY must be set for RS* auth in prod.")
        if current.auth_private_key:
            errors.append("LOCATION_AUTH_PRIVATE_KEY must not be set in prod; signing belongs to identity-service.")
    if not current.database_url or current.database_url == DEFAULT_DATABASE_URL:
        errors.append("LOCATION_DATABASE_URL must be set to a non-default value in prod.")
    if not current.mapbox_api_key:
        errors.append("LOCATION_MAPBOX_API_KEY must be set in prod.")
    if current.enable_ors_validation:
        if not current.ors_api_key:
            errors.append("LOCATION_ORS_API_KEY must be set when LOCATION_ENABLE_ORS_VALIDATION=true in prod.")
        if not current.ors_base_url:
            errors.append("LOCATION_ORS_BASE_URL must be set when LOCATION_ENABLE_ORS_VALIDATION=true in prod.")
    if current.provider_timeout_ms <= 0:
        errors.append("LOCATION_PROVIDER_TIMEOUT_MS must be greater than zero.")

    if errors:
        raise ValueError("Production settings invalid: " + " ".join(errors))
