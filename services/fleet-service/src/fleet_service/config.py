"""Application configuration via environment variables (Fleet Service v1.5, Section 13)."""

from typing import Literal

from pydantic_settings import BaseSettings

DEFAULT_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/fleet_service"


class Settings(BaseSettings):
    """Fleet Service configuration loaded from environment variables."""

    # --- Service identity ---
    service_name: str = "fleet-service"
    service_version: str = "0.1.0"
    service_port: int = 8102
    environment: Literal["dev", "test", "prod"] = "dev"
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"

    # --- Database ---
    database_url: str = DEFAULT_DATABASE_URL

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = 10
    redis_socket_timeout: float = 1.0
    redis_retry_on_timeout: bool = True

    # --- Auth ---
    auth_jwt_algorithm: str = "RS256"
    auth_issuer: str = "lojinext-platform"
    auth_audience: str = "lojinext-platform"
    auth_public_key: str = ""
    auth_private_key: str = ""
    auth_jwks_url: str = ""
    auth_jwks_cache_ttl_seconds: int = 300
    auth_service_token_url: str = ""
    auth_service_client_id: str = "fleet-service"
    auth_service_client_secret: str = ""
    platform_jwt_secret: str | None = None

    # --- Feature flags ---
    enable_hard_delete: bool = False
    enable_trip_references: bool = False

    # --- Dependencies: Driver Service ---
    driver_service_base_url: str = "http://localhost:8104"

    # --- Dependencies: Trip Service ---
    trip_service_base_url: str = "http://localhost:8101"

    # --- HTTP Client ---
    http_connect_timeout: float = 0.5
    http_read_timeout: float = 0.8
    http_total_timeout: float = 1.5
    http_max_connections: int = 20
    http_max_keepalive: int = 10

    # --- Circuit breaker ---
    breaker_open_threshold: int = 5
    breaker_half_open_after_seconds: int = 30
    breaker_close_threshold: int = 3

    # --- Outbox ---
    outbox_poll_interval_seconds: int = 5
    outbox_batch_size: int = 50
    outbox_max_retries: int = 10
    outbox_worker_enabled: bool = True
    schema_event_version: int = 1

    # --- Heartbeat ---
    heartbeat_interval_seconds: int = 30
    heartbeat_stale_seconds: int = 90

    # --- Idempotency ---
    idempotency_ttl_hours: int = 24
    idempotency_cleanup_interval_hours: int = 6

    # --- Pagination ---
    default_page_size: int = 20
    max_page_size: int = 100

    # --- Broker ---
    broker_type: Literal["kafka", "log", "noop"] | None = None
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic: str = "fleet.events.v1"
    kafka_client_id: str = "fleet-service"
    kafka_security_protocol: str = "PLAINTEXT"
    allow_plaintext_in_prod: bool = False
    kafka_acks: str = "all"
    kafka_enable_idempotence: bool = True
    kafka_linger_ms: int = 5
    kafka_batch_size: int = 32768
    kafka_compression_type: str = "lz4"
    kafka_sasl_mechanism: str | None = None
    kafka_sasl_username: str | None = None
    kafka_sasl_password: str | None = None

    @property
    def resolved_broker_type(self) -> Literal["kafka", "log", "noop"]:
        """Resolve the effective broker type based on environment defaults."""
        bt = self.broker_type
        if bt is not None:
            return bt
        if self.environment == "prod":
            return "kafka"
        if self.environment == "test":
            return "noop"
        return "log"

    model_config = {"env_prefix": "FLEET_", "env_file": ".env", "extra": "ignore"}


settings = Settings()


def validate_prod_settings(current: Settings) -> None:
    """Fail fast when production settings are insecure or missing."""
    if current.environment != "prod":
        return

    errors: list[str] = []
    if current.auth_jwt_algorithm.upper() != "RS256":
        errors.append("FLEET_AUTH_JWT_ALGORITHM must be RS256 in prod.")
    if not current.auth_issuer:
        errors.append("FLEET_AUTH_ISSUER must be set for RS256 auth in prod.")
    if not current.auth_audience:
        errors.append("FLEET_AUTH_AUDIENCE must be set for RS256 auth in prod.")
    if not current.auth_jwks_url:
        errors.append("FLEET_AUTH_JWKS_URL must be set for RS256 auth in prod.")
    if current.auth_public_key:
        errors.append("FLEET_AUTH_PUBLIC_KEY must not be set in prod; verification must use JWKS.")
    if current.auth_private_key:
        errors.append("FLEET_AUTH_PRIVATE_KEY must not be set in prod; signing belongs to identity-service.")
    if not current.auth_service_token_url:
        errors.append("FLEET_AUTH_SERVICE_TOKEN_URL must be set for outbound auth in prod.")
    if not current.auth_service_client_secret:
        errors.append("FLEET_AUTH_SERVICE_CLIENT_SECRET must be set for outbound auth in prod.")
    if not current.database_url or current.database_url == DEFAULT_DATABASE_URL:
        errors.append("FLEET_DATABASE_URL must be set to a non-default value in prod.")
    if current.resolved_broker_type != "kafka":
        errors.append("FLEET_BROKER_TYPE must resolve to kafka in prod.")
    if not current.kafka_bootstrap_servers or current.kafka_bootstrap_servers == "localhost:9092":
        errors.append("FLEET_KAFKA_BOOTSTRAP_SERVERS must be set to a non-default value in prod.")
    if current.kafka_security_protocol == "PLAINTEXT" and not current.allow_plaintext_in_prod:
        errors.append(
            "FLEET_KAFKA_SECURITY_PROTOCOL cannot be PLAINTEXT in prod without FLEET_ALLOW_PLAINTEXT_IN_PROD."
        )
    if current.platform_jwt_secret:
        errors.append("FLEET_PLATFORM_JWT_SECRET must not be set in prod; use RS256/JWKS only.")
    if not current.redis_url or "localhost" in current.redis_url:
        errors.append("FLEET_REDIS_URL must be set to a production-ready value.")

    if errors:
        raise ValueError("Production settings invalid: " + " ".join(errors))
