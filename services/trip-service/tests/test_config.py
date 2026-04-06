"""Configuration validation tests."""

from __future__ import annotations

import pytest

from trip_service.config import DEFAULT_DATABASE_URL, DEFAULT_KAFKA_BOOTSTRAP, Settings, validate_prod_settings


def _base_prod_settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="prod",
        auth_jwt_algorithm="RS256",
        auth_issuer="lojinext-platform",
        auth_audience="lojinext-platform",
        auth_jwks_url="http://identity-api:8105/.well-known/jwks.json",
        auth_service_token_url="http://identity-api:8105/auth/v1/token/service",
        auth_service_client_id="trip-service",
        auth_service_client_secret="trip-client-secret",
        database_url="postgresql+asyncpg://prod:prod@db:5432/trip_service",
        broker_type="kafka",
        kafka_bootstrap_servers="kafka:9092",
        kafka_security_protocol="SASL_SSL",
    )


def test_validate_prod_rejects_hs256_runtime() -> None:
    settings = _base_prod_settings()
    settings.auth_jwt_algorithm = "HS256"
    with pytest.raises(ValueError, match="TRIP_AUTH_JWT_ALGORITHM"):
        validate_prod_settings(settings)


def test_validate_prod_rejects_default_database_url() -> None:
    settings = _base_prod_settings()
    settings.database_url = DEFAULT_DATABASE_URL
    with pytest.raises(ValueError, match="TRIP_DATABASE_URL"):
        validate_prod_settings(settings)


def test_validate_prod_rejects_default_kafka_bootstrap() -> None:
    settings = _base_prod_settings()
    settings.kafka_bootstrap_servers = DEFAULT_KAFKA_BOOTSTRAP
    with pytest.raises(ValueError, match="TRIP_KAFKA_BOOTSTRAP_SERVERS"):
        validate_prod_settings(settings)


def test_validate_prod_rejects_plaintext_kafka() -> None:
    settings = _base_prod_settings()
    settings.kafka_security_protocol = "PLAINTEXT"
    with pytest.raises(ValueError, match="TRIP_KAFKA_SECURITY_PROTOCOL"):
        validate_prod_settings(settings)


def test_validate_prod_requires_broker_type() -> None:
    settings = _base_prod_settings()
    settings.broker_type = None
    with pytest.raises(ValueError, match="TRIP_BROKER_TYPE"):
        validate_prod_settings(settings)


def test_validate_prod_rejects_rs256_without_issuer_and_audience() -> None:
    settings = _base_prod_settings()
    settings.auth_issuer = ""
    settings.auth_audience = ""

    with pytest.raises(ValueError, match="TRIP_AUTH_ISSUER"):
        validate_prod_settings(settings)


def test_validate_prod_rejects_rs256_without_jwks_url() -> None:
    settings = _base_prod_settings()
    settings.auth_jwks_url = ""

    with pytest.raises(ValueError, match="TRIP_AUTH_JWKS_URL"):
        validate_prod_settings(settings)


def test_validate_prod_rejects_rs256_without_outbound_credentials() -> None:
    settings = _base_prod_settings()
    settings.auth_service_token_url = ""
    settings.auth_service_client_secret = ""

    with pytest.raises(ValueError, match="TRIP_AUTH_SERVICE_TOKEN_URL"):
        validate_prod_settings(settings)
