"""Application configuration via environment variables (spec Section 9)."""

from typing import Literal

from pydantic_settings import BaseSettings

DEFAULT_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/driver_service"
DEFAULT_AUTH_JWT_SECRET = "driver-service-dev-secret-please-change-me-32b"


class Settings(BaseSettings):
    """Driver Service configuration loaded from environment variables."""

    # --- Service identity ---
    service_name: str = "driver-service"
    service_port: int = 8104
    environment: Literal["dev", "test", "prod"] = "dev"

    # --- Database ---
    database_url: str = DEFAULT_DATABASE_URL

    # --- Auth ---
    auth_jwt_secret: str = DEFAULT_AUTH_JWT_SECRET
    auth_jwt_algorithm: str = "HS256"

    # --- Phone normalization ---
    default_phone_region: str = "TR"

    # --- Feature flags ---
    enable_hard_delete: bool = False
    enable_merge_endpoint: bool = False

    # --- Outbox ---
    outbox_publish_batch_size: int = 100
    outbox_retry_max: int = 20
    outbox_worker_enabled: bool = True
    outbox_poll_interval_seconds: int = 5

    # --- Pagination ---
    default_page_size: int = 50
    max_page_size: int = 200

    # --- Maintenance / Imports ---
    maintenance_poll_interval_seconds: int = 60

    # --- Dependencies ---
    trip_service_base_url: str = "http://localhost:8101"
    dependency_timeout_seconds: float = 5.0

    # --- Logging ---
    log_mask_phone: bool = True

    # --- Broker ---
    broker_type: Literal["kafka", "log", "noop"] | None = None
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic: str = "driver.events.v1"
    kafka_client_id: str = "driver-service"
    kafka_security_protocol: str = "PLAINTEXT"
    allow_plaintext_in_prod: bool = False
    kafka_sasl_mechanism: str | None = None
    kafka_sasl_username: str | None = None
    kafka_sasl_password: str | None = None

    @property
    def resolved_broker_type(self) -> Literal["kafka", "log", "noop"]:
        """Resolve the effective broker type based on environment defaults."""
        if self.broker_type is not None:
            return self.broker_type
        if self.environment == "prod":
            return "kafka"
        if self.environment == "test":
            return "noop"
        return "log"

    model_config = {"env_prefix": "DRIVER_", "env_file": ".env", "extra": "ignore"}


settings = Settings()


def validate_prod_settings(current: Settings) -> None:
    """Fail fast when production settings are insecure or missing."""
    if current.environment != "prod":
        return

    errors: list[str] = []
    if not current.auth_jwt_secret or current.auth_jwt_secret == DEFAULT_AUTH_JWT_SECRET:
        errors.append("DRIVER_AUTH_JWT_SECRET must be set to a non-default value in prod.")
    if not current.database_url or current.database_url == DEFAULT_DATABASE_URL:
        errors.append("DRIVER_DATABASE_URL must be set to a non-default value in prod.")
    if current.broker_type is None:
        errors.append("DRIVER_BROKER_TYPE must be explicitly set in prod.")
    if not current.kafka_bootstrap_servers or current.kafka_bootstrap_servers == "localhost:9092":
        errors.append("DRIVER_KAFKA_BOOTSTRAP_SERVERS must be set to a non-default value in prod.")
    if current.kafka_security_protocol == "PLAINTEXT" and not current.allow_plaintext_in_prod:
        errors.append(
            "DRIVER_KAFKA_SECURITY_PROTOCOL cannot be PLAINTEXT in prod without DRIVER_ALLOW_PLAINTEXT_IN_PROD."
        )

    if errors:
        raise ValueError("Production settings invalid: " + " ".join(errors))
