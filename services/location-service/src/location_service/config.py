"""Application configuration via environment variables.

All configuration is read from environment. Never hardcoded.
Implements v0.7 Section 13: Environment Variables.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Location Service configuration loaded from environment variables."""

    # --- Service Identity (Section 1) ---
    service_name: str = "location-service"
    service_port: int = 8103

    # --- Database ---
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/location_service"

    # --- API ---
    api_version: str = "v1"
    profile_default: str = "TIR"

    # --- Mapbox (Section 9.1, 9.2) ---
    mapbox_api_key: str = ""
    mapbox_directions_base_url: str = "https://api.mapbox.com/directions/v5"
    mapbox_raster_base_url: str = "https://api.mapbox.com/v4"

    # --- ORS (Section 9.3) ---
    ors_api_key: str = ""
    ors_base_url: str = ""
    enable_ors_validation: bool = True

    # --- Provider Retry (Section 9) ---
    provider_timeout_ms: int = 4000
    provider_retry_max: int = 3

    # --- Segment & Elevation (Sections 5.9, 6.4) ---
    segment_max_length_m: int = 200
    elevation_sampling_max_spacing_m: int = 30
    elevation_max_tiles: int = 2000

    # --- Validation Thresholds (Section 5.9) ---
    distance_delta_warning_pct: float = 5.0
    distance_delta_fail_pct: float = 15.0
    duration_delta_warning_pct: float = 10.0
    duration_delta_fail_pct: float = 20.0
    endpoint_parity_tolerance_m: float = 25.0
    known_speed_limit_ratio_warning: float = 0.85
    known_speed_limit_ratio_fail: float = 0.50

    # --- Hard Delete (Section 7.17) ---
    hard_delete_grace_period_days: int = 30

    # --- Idempotency (Section 4.15) ---
    idempotency_ttl_hours: int = 24

    # --- Scheduled Refresh (Section 13) ---
    monthly_refresh_cron: str = ""

    # --- Object Storage (Section 11) ---
    import_storage_bucket: str = ""
    export_storage_bucket: str = ""
    export_file_ttl_hours: int = 24
    storage_backend: str = "local"
    storage_local_path: str = "./storage"

    # --- Bulk Refresh (Section 8) ---
    enable_bulk_refresh: bool = True

    # --- Stuck Run Recovery (Section 4.7) ---
    run_stuck_sla_minutes: int = 30

    # --- Environment ---
    env_name: str = "dev"

    model_config = {"env_prefix": "LOCATION_", "env_file": ".env", "extra": "ignore"}


settings = Settings()
