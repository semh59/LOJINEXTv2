"""Application configuration via environment variables."""

from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Trip Service configuration loaded from environment variables."""

    service_name: str = "trip-service"
    service_port: int = 8101
    environment: Literal["dev", "test", "prod"] = "dev"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/trip_service"

    fleet_service_url: str = "http://localhost:8102"
    location_service_url: str = "http://localhost:8103"
    dependency_timeout_seconds: float = 5.0
    auth_jwt_secret: str = "trip-service-dev-secret-please-change-me-32b"
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
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic: str = "trip.events.v1"
    kafka_client_id: str = "trip-service"
    kafka_security_protocol: str = "PLAINTEXT"
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
