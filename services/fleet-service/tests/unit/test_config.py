from __future__ import annotations

from fleet_service.config import Settings, validate_prod_settings


def test_validate_prod_settings_accepts_rs256_without_legacy_dependency_secrets() -> None:
    settings = Settings(
        environment="prod",
        database_url="postgresql+asyncpg://fleet:fleet@db:5432/fleet_service",
        auth_jwt_algorithm="RS256",
        auth_issuer="lojinext-platform",
        auth_audience="lojinext-platform",
        auth_jwks_url="http://identity-api:8105/.well-known/jwks.json",
        auth_service_token_url="http://identity-api:8105/auth/v1/token/service",
        auth_service_client_secret="fleet-client-secret",
        broker_type="kafka",
        kafka_bootstrap_servers="redpanda:9092",
        allow_plaintext_in_prod=True,
    )

    validate_prod_settings(settings)
