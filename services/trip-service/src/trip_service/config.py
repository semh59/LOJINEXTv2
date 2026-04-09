"""Application configuration via environment variables."""

from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings

DEFAULT_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/trip_service"
DEFAULT_KAFKA_BOOTSTRAP = "localhost:9092"


class Settings(BaseSettings):
    """Trip Service configuration loaded from environment variables."""

    service_name: str = "trip-service"
    service_version: str = "0.1.0"
    service_port: int = 8101
    environment: Literal["dev", "test", "prod"] = "dev"

    database_url: str = DEFAULT_DATABASE_URL

    fleet_service_url: str = "http://localhost:8102"
    location_service_url: str = "http://localhost:8103"
    dependency_timeout_seconds: float = 5.0
    auth_jwt_algorithm: str = "RS256"
    auth_issuer: str = "lojinext-platform"
    auth_audience: str = "lojinext-platform"
    auth_public_key: str = ""
    auth_private_key: str = ""
    auth_jwks_url: str = ""
    auth_jwks_cache_ttl_seconds: int = 300
    auth_service_token_url: str = ""
    auth_service_client_id: str = "trip-service"
    auth_service_client_secret: str = ""
    allow_legacy_actor_headers: bool = False

    enrichment_claim_ttl_seconds: int = 300
    enrichment_max_attempts: int = 5
    enrichment_poll_interval_seconds: int = 10
    worker_heartbeat_timeout_seconds: int = 30

    outbox_relay_poll_interval_seconds: int = 5
    outbox_relay_claim_ttl_seconds: int = 60
    outbox_relay_max_failures: int = 10

    idempotency_retention_hours: int = 24

    # CORS — comma-separated list of allowed origins for browser frontends.
    # Dev default allows common local frontend ports. Set explicitly in prod.
    cors_allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:5173",
        "http://localhost:8080",
    ]

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

    @model_validator(mode="after")
    def _validate_timeout_vs_claim_ttl(self) -> "Settings":
        """Ensure the enrichment claim TTL covers worst-case HTTP retry duration."""
        worst_case_s = self.dependency_timeout_seconds * 3
        if worst_case_s >= self.enrichment_claim_ttl_seconds:
            raise ValueError(
                f"enrichment_claim_ttl_seconds ({self.enrichment_claim_ttl_seconds}s) must be greater than "
                f"dependency_timeout_seconds * 3 ({worst_case_s}s). "
                "Otherwise a slow retry can expire the claim before the worker finishes."
            )
        return self

    model_config = {"env_prefix": "TRIP_", "env_file": ".env", "extra": "ignore"}


settings = Settings()


def validate_prod_settings(current: Settings) -> None:
    """Fail fast when production settings are insecure or missing."""
    if current.environment != "prod":
        return

    errors: list[str] = []
    if current.auth_jwt_algorithm.upper() != "RS256":
        errors.append("TRIP_AUTH_JWT_ALGORITHM must be RS256 in prod.")
    if not current.auth_issuer:
        errors.append("TRIP_AUTH_ISSUER must be set for RS256 auth in prod.")
    if not current.auth_audience:
        errors.append("TRIP_AUTH_AUDIENCE must be set for RS256 auth in prod.")
    if not current.auth_jwks_url:
        errors.append("TRIP_AUTH_JWKS_URL must be set for RS256 auth in prod.")
    if current.auth_public_key:
        errors.append("TRIP_AUTH_PUBLIC_KEY must not be set in prod; verification must use JWKS.")
    if current.auth_private_key:
        errors.append("TRIP_AUTH_PRIVATE_KEY must not be set in prod; signing belongs to identity-service.")
    if not current.auth_service_token_url:
        errors.append("TRIP_AUTH_SERVICE_TOKEN_URL must be set for RS256 outbound auth in prod.")
    if not current.auth_service_client_id:
        errors.append("TRIP_AUTH_SERVICE_CLIENT_ID must be set for RS256 outbound auth in prod.")
    if not current.auth_service_client_secret:
        errors.append("TRIP_AUTH_SERVICE_CLIENT_SECRET must be set for RS256 outbound auth in prod.")
    if not current.database_url or current.database_url == DEFAULT_DATABASE_URL:
        errors.append("TRIP_DATABASE_URL must be set to a non-default value in prod.")
    if current.broker_type is None:
        errors.append("TRIP_BROKER_TYPE must be explicitly set in prod.")
    if not current.kafka_bootstrap_servers or current.kafka_bootstrap_servers == DEFAULT_KAFKA_BOOTSTRAP:
        errors.append("TRIP_KAFKA_BOOTSTRAP_SERVERS must be set to a non-default value in prod.")
    if current.kafka_security_protocol == "PLAINTEXT" and not current.allow_plaintext_in_prod:
        errors.append("TRIP_KAFKA_SECURITY_PROTOCOL cannot be PLAINTEXT in prod without TRIP_ALLOW_PLAINTEXT_IN_PROD.")

    _dev_origins = {"http://localhost:3000", "http://localhost:3001", "http://localhost:5173", "http://localhost:8080"}
    if set(current.cors_allowed_origins) == _dev_origins or not current.cors_allowed_origins:
        errors.append("TRIP_CORS_ALLOWED_ORIGINS must be set to production frontend URLs in prod.")

    if errors:
        raise ValueError("Production settings invalid: " + " ".join(errors))
