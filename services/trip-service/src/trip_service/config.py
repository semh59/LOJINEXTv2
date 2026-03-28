"""Application configuration via environment variables."""

from typing import Literal

from pydantic_settings import BaseSettings

DEFAULT_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/trip_service"
DEFAULT_AUTH_JWT_SECRET = "trip-service-dev-secret-please-change-me-32b"
DEFAULT_KAFKA_BOOTSTRAP = "localhost:9092"


class Settings(BaseSettings):
    """Trip Service configuration loaded from environment variables."""

    service_name: str = "trip-service"
    service_port: int = 8101
    environment: Literal["dev", "test", "prod"] = "dev"

    database_url: str = DEFAULT_DATABASE_URL

    fleet_service_url: str = "http://localhost:8102"
    location_service_url: str = "http://localhost:8103"
    dependency_timeout_seconds: float = 5.0
    auth_jwt_secret: str = DEFAULT_AUTH_JWT_SECRET
    auth_jwt_algorithm: str = "HS256"
    allow_legacy_actor_headers: bool = False

    enrichment_claim_ttl_seconds: int = 300
    enrichment_max_attempts: int = 5
    enrichment_poll_interval_seconds: int = 10
    worker_heartbeat_timeout_seconds: int = 30

    outbox_relay_poll_interval_seconds: int = 5
    outbox_relay_max_failures: int = 10

    idempotency_retention_hours: int = 24
    broker_type: Literal["kafka", "log", "noop"] | None = None
    kafka_bootstrap_servers: str = DEFAULT_KAFKA_BOOTSTRAP
    kafka_topic: str = "trip.events.v1"
    kafka_client_id: str = "trip-service"
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

    model_config = {"env_prefix": "TRIP_", "env_file": ".env", "extra": "ignore"}


settings = Settings()


def validate_prod_settings(current: Settings) -> None:
    """Fail fast when production settings are insecure or missing."""
    if current.environment != "prod":
        return

    errors: list[str] = []
    if not current.auth_jwt_secret or current.auth_jwt_secret == DEFAULT_AUTH_JWT_SECRET:
        errors.append("TRIP_AUTH_JWT_SECRET must be set to a non-default value in prod.")
    if not current.database_url or current.database_url == DEFAULT_DATABASE_URL:
        errors.append("TRIP_DATABASE_URL must be set to a non-default value in prod.")
    if current.broker_type is None:
        errors.append("TRIP_BROKER_TYPE must be explicitly set in prod.")
    if not current.kafka_bootstrap_servers or current.kafka_bootstrap_servers == DEFAULT_KAFKA_BOOTSTRAP:
        errors.append("TRIP_KAFKA_BOOTSTRAP_SERVERS must be set to a non-default value in prod.")
    if current.kafka_security_protocol == "PLAINTEXT" and not current.allow_plaintext_in_prod:
        errors.append("TRIP_KAFKA_SECURITY_PROTOCOL cannot be PLAINTEXT in prod without TRIP_ALLOW_PLAINTEXT_IN_PROD.")

    if errors:
        raise ValueError("Production settings invalid: " + " ".join(errors))
