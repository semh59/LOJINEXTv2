"""Application configuration via environment variables.

All configuration is read from environment. Never hardcoded.
See V8 Section 24: deferred deployment-level decisions are env-configured.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Trip Service configuration loaded from environment variables."""

    # --- Service Identity (V8 Section 2) ---
    service_name: str = "trip-service"
    service_port: int = 8101

    # --- Database ---
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/trip_service"

    # --- External Service URLs (V8 Section 7) ---
    fleet_service_url: str = "http://localhost:8102"
    location_service_url: str = "http://localhost:8103"
    weather_service_url: str = "http://localhost:8104"

    # --- Object Storage ---
    storage_backend: str = "local"  # "local" or "s3"
    storage_local_path: str = "./storage"
    storage_s3_bucket: str = ""
    storage_s3_region: str = ""

    # --- Enrichment Worker (V8 Section 13) ---
    enrichment_claim_ttl_seconds: int = 300  # 5 minutes recommended default
    enrichment_max_attempts: int = 5
    enrichment_poll_interval_seconds: int = 10

    # --- Outbox Relay (V8 Section 14) ---
    outbox_relay_poll_interval_seconds: int = 5
    outbox_relay_max_failures: int = 10

    # --- Idempotency (V8 Section 15) ---
    idempotency_retention_hours: int = 24

    # --- Export (V8 Section 17) ---
    export_presigned_url_ttl_hours: int = 24

    model_config = {"env_prefix": "TRIP_", "env_file": ".env", "extra": "ignore"}


settings = Settings()
