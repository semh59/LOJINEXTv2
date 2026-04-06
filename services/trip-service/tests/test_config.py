"""Configuration validation tests."""

from __future__ import annotations

import pytest

from trip_service.config import (
    DEFAULT_AUTH_JWT_SECRET,
    DEFAULT_DATABASE_URL,
    DEFAULT_KAFKA_BOOTSTRAP,
    Settings,
    validate_prod_settings,
)


def _base_prod_settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="prod",
        auth_jwt_secret="prod-secret-32b-min",
        database_url="postgresql+asyncpg://prod:prod@db:5432/trip_service",
        broker_type="kafka",
        kafka_bootstrap_servers="kafka:9092",
        kafka_security_protocol="SASL_SSL",
    )


def test_validate_prod_rejects_default_jwt_secret():
    settings = _base_prod_settings()
    settings.auth_jwt_secret = DEFAULT_AUTH_JWT_SECRET
    with pytest.raises(ValueError, match="TRIP_AUTH_JWT_SECRET"):
        validate_prod_settings(settings)


def test_validate_prod_rejects_default_database_url():
    settings = _base_prod_settings()
    settings.database_url = DEFAULT_DATABASE_URL
    with pytest.raises(ValueError, match="TRIP_DATABASE_URL"):
        validate_prod_settings(settings)


def test_validate_prod_rejects_default_kafka_bootstrap():
    settings = _base_prod_settings()
    settings.kafka_bootstrap_servers = DEFAULT_KAFKA_BOOTSTRAP
    with pytest.raises(ValueError, match="TRIP_KAFKA_BOOTSTRAP_SERVERS"):
        validate_prod_settings(settings)


def test_validate_prod_rejects_plaintext_kafka():
    settings = _base_prod_settings()
    settings.kafka_security_protocol = "PLAINTEXT"
    with pytest.raises(ValueError, match="TRIP_KAFKA_SECURITY_PROTOCOL"):
        validate_prod_settings(settings)


def test_validate_prod_requires_broker_type():
    settings = _base_prod_settings()
    settings.broker_type = None
    with pytest.raises(ValueError, match="TRIP_BROKER_TYPE"):
        validate_prod_settings(settings)


def test_validate_prod_rejects_platform_jwt_bridge(monkeypatch: pytest.MonkeyPatch):
    settings = _base_prod_settings()
    monkeypatch.setenv("PLATFORM_JWT_SECRET", "bridge-secret")
    with pytest.raises(ValueError, match="PLATFORM_JWT_SECRET"):
        validate_prod_settings(settings)


def test_validate_prod_rejects_rs256_without_issuer_and_audience() -> None:
    settings = _base_prod_settings()
    settings.auth_jwt_algorithm = "RS256"
    settings.auth_jwt_secret = ""
    settings.auth_public_key = "public-key"
    settings.auth_service_token_url = "https://identity.example.com/oauth/token"
    settings.auth_service_client_secret = "client-secret"
    settings.auth_issuer = ""
    settings.auth_audience = ""

    with pytest.raises(ValueError, match="TRIP_AUTH_ISSUER"):
        validate_prod_settings(settings)


def test_validate_prod_rejects_rs256_without_outbound_credentials() -> None:
    settings = _base_prod_settings()
    settings.auth_jwt_algorithm = "RS256"
    settings.auth_jwt_secret = ""
    settings.auth_public_key = "public-key"
    settings.auth_issuer = "https://identity.example.com/"
    settings.auth_audience = "lojinext-platform"
    settings.auth_service_token_url = ""
    settings.auth_service_client_secret = ""

    with pytest.raises(ValueError, match="TRIP_AUTH_SERVICE_TOKEN_URL"):
        validate_prod_settings(settings)
