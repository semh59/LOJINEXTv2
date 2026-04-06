"""Configuration validation tests for driver-service."""

from __future__ import annotations

import pytest

from driver_service.config import DEFAULT_DATABASE_URL, Settings, validate_prod_settings


def _candidate(**overrides: object) -> Settings:
    base = Settings(
        _env_file=None,
        environment="prod",
        auth_jwt_algorithm="RS256",
        auth_issuer="lojinext-platform",
        auth_audience="lojinext-platform",
        auth_jwks_url="http://identity-api:8105/.well-known/jwks.json",
        auth_service_audience="lojinext-platform",
        auth_service_token_url="http://identity-api:8105/auth/v1/token/service",
        auth_service_client_id="driver-service",
        auth_service_client_secret="driver-client-secret",
        database_url="postgresql+asyncpg://driver:driver@db:5432/driver_service",
        broker_type="kafka",
        kafka_bootstrap_servers="redpanda:9092",
        allow_plaintext_in_prod=True,
    )
    return base.model_copy(update=overrides)


def test_prod_validation_rejects_hs256() -> None:
    with pytest.raises(ValueError, match="DRIVER_AUTH_JWT_ALGORITHM"):
        validate_prod_settings(_candidate(auth_jwt_algorithm="HS256"))


def test_prod_validation_requires_jwks_url() -> None:
    with pytest.raises(ValueError, match="DRIVER_AUTH_JWKS_URL"):
        validate_prod_settings(_candidate(auth_jwks_url=""))


def test_prod_validation_requires_outbound_credentials() -> None:
    with pytest.raises(ValueError, match="DRIVER_AUTH_SERVICE_TOKEN_URL"):
        validate_prod_settings(_candidate(auth_service_token_url="", auth_service_client_secret=""))


def test_prod_validation_rejects_default_database_url() -> None:
    with pytest.raises(ValueError, match="DRIVER_DATABASE_URL"):
        validate_prod_settings(_candidate(database_url=DEFAULT_DATABASE_URL))
