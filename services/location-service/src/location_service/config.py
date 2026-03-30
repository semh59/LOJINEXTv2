"""Application configuration via environment variables."""

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
    processing_poll_interval_seconds: float = 5.0
    processing_claim_ttl_seconds: int = 300
    worker_heartbeat_timeout_seconds: int = 60

    segment_max_length_m: int = 200
    elevation_sampling_max_spacing_m: int = 30
    elevation_max_tiles: int = 2000

    distance_delta_warning_pct: float = 5.0
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
    if not current.auth_jwt_secret or current.auth_jwt_secret == DEFAULT_AUTH_JWT_SECRET:
        errors.append("LOCATION_AUTH_JWT_SECRET must be set to a non-default value in prod.")
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
    if current.provider_retry_max < 0:
        errors.append("LOCATION_PROVIDER_RETRY_MAX cannot be negative.")
    if current.provider_probe_ttl_seconds < 0:
        errors.append("LOCATION_PROVIDER_PROBE_TTL_SECONDS cannot be negative.")
    if current.processing_poll_interval_seconds <= 0:
        errors.append("LOCATION_PROCESSING_POLL_INTERVAL_SECONDS must be greater than zero.")
    if current.processing_claim_ttl_seconds <= 0:
        errors.append("LOCATION_PROCESSING_CLAIM_TTL_SECONDS must be greater than zero.")
    if current.worker_heartbeat_timeout_seconds <= 0:
        errors.append("LOCATION_WORKER_HEARTBEAT_TIMEOUT_SECONDS must be greater than zero.")

    if errors:
        raise ValueError("Production settings invalid: " + " ".join(errors))
