"""Application configuration via environment variables."""

from typing import Literal

from pydantic_settings import BaseSettings

DEFAULT_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/location_service"
DEFAULT_MAPBOX_DIRECTIONS_BASE_URL = "https://api.mapbox.com/directions/v5"
DEFAULT_MAPBOX_RASTER_BASE_URL = "https://api.mapbox.com/v4"
DEFAULT_ORS_BASE_URL = "https://api.openrouteservice.org/v2/directions/driving-hgv"


class Settings(BaseSettings):
    """Location Service configuration loaded from environment variables."""

    service_name: str = "location-service"
    service_version: str = "0.1.0"
    service_port: int = 8103
    environment: Literal["dev", "test", "prod"] = "dev"

    database_url: str = DEFAULT_DATABASE_URL

    api_version: str = "v1"
    profile_default: str = "TIR"

    auth_jwt_algorithm: str = "RS256"
    auth_issuer: str = "lojinext-platform"
    auth_audience: str = "lojinext-platform"
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
    provider_retry_max: int = 3
    provider_probe_ttl_seconds: int = 30
    provider_probe_origin_lng: float = 28.9784
    provider_probe_origin_lat: float = 41.0082
    provider_probe_dest_lng: float = 28.9905
    provider_probe_dest_lat: float = 41.0151
    distance_delta_fail_pct: float = 15.0
    distance_delta_warning_pct: float = 5.0
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
    processing_poll_interval_seconds: int = 5
    processing_claim_ttl_seconds: int = 300
    processing_max_attempts: int = 5
    worker_heartbeat_timeout_seconds: int = 60
    outbox_poll_interval_seconds: int = 5
    outbox_publish_batch_size: int = 50
    outbox_retry_max: int = 5
    kafka_topic: str = "location-events"
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_client_id: str = "location-service"
    kafka_security_protocol: str = "PLAINTEXT"
    ignore_provider_health: bool = False
    platform_jwt_secret: str | None = None
    allow_plaintext_in_prod: bool = False

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
    if current.auth_jwt_algorithm.upper() != "RS256":
        errors.append("LOCATION_AUTH_JWT_ALGORITHM must be RS256 in prod.")
    if not current.auth_issuer:
        errors.append("LOCATION_AUTH_ISSUER must be set for RS256 auth in prod.")
    if not current.auth_audience:
        errors.append("LOCATION_AUTH_AUDIENCE must be set for RS256 auth in prod.")
    if not current.auth_jwks_url:
        errors.append("LOCATION_AUTH_JWKS_URL must be set for RS256 auth in prod.")
    if current.auth_public_key:
        errors.append("LOCATION_AUTH_PUBLIC_KEY must not be set in prod; verification must use JWKS.")
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
    if current.platform_jwt_secret is not None:
        errors.append("LOCATION_PLATFORM_JWT_SECRET must not be set in prod; verification must use JWKS.")
    if current.kafka_security_protocol == "PLAINTEXT" and not current.allow_plaintext_in_prod:
        errors.append(
            "LOCATION_KAFKA_SECURITY_PROTOCOL cannot be PLAINTEXT in prod without LOCATION_ALLOW_PLAINTEXT_IN_PROD."
        )

    if errors:
        raise ValueError("Production settings invalid: " + " ".join(errors))
