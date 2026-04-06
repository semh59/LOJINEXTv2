from __future__ import annotations

import pytest

from location_service.config import DEFAULT_DATABASE_URL, settings, validate_prod_settings


def _candidate(**overrides: object):
    base = settings.model_copy(deep=True)
    return base.model_copy(update=overrides)


def test_prod_validation_rejects_hs256_runtime() -> None:
    candidate = _candidate(
        environment="prod",
        auth_jwt_algorithm="HS256",
        database_url="postgresql+asyncpg://user:pass@db.example.com:5432/location",
        mapbox_api_key="mapbox-key",
        enable_ors_validation=False,
    )

    with pytest.raises(ValueError, match="LOCATION_AUTH_JWT_ALGORITHM"):
        validate_prod_settings(candidate)


def test_prod_validation_rejects_default_database_url() -> None:
    candidate = _candidate(
        environment="prod",
        database_url=DEFAULT_DATABASE_URL,
        mapbox_api_key="mapbox-key",
        enable_ors_validation=False,
    )

    with pytest.raises(ValueError, match="LOCATION_DATABASE_URL"):
        validate_prod_settings(candidate)


def test_prod_validation_requires_jwks_issuer_and_audience() -> None:
    candidate = _candidate(
        environment="prod",
        auth_issuer="",
        auth_audience="",
        auth_jwks_url="",
        database_url="postgresql+asyncpg://user:pass@db.example.com:5432/location",
        mapbox_api_key="mapbox-key",
        enable_ors_validation=False,
    )

    with pytest.raises(ValueError, match="LOCATION_AUTH_ISSUER"):
        validate_prod_settings(candidate)


def test_prod_validation_requires_mapbox_key() -> None:
    candidate = _candidate(
        environment="prod",
        database_url="postgresql+asyncpg://user:pass@db.example.com:5432/location",
        mapbox_api_key="",
        enable_ors_validation=False,
    )

    with pytest.raises(ValueError, match="LOCATION_MAPBOX_API_KEY"):
        validate_prod_settings(candidate)


def test_prod_validation_requires_ors_settings_when_enabled() -> None:
    candidate = _candidate(
        environment="prod",
        database_url="postgresql+asyncpg://user:pass@db.example.com:5432/location",
        mapbox_api_key="mapbox-key",
        enable_ors_validation=True,
        ors_api_key="",
        ors_base_url="",
    )

    with pytest.raises(ValueError, match="LOCATION_ORS_API_KEY"):
        validate_prod_settings(candidate)


def test_prod_validation_accepts_complete_rs256_config() -> None:
    candidate = _candidate(
        environment="prod",
        auth_jwt_algorithm="RS256",
        auth_issuer="lojinext-platform",
        auth_audience="lojinext-platform",
        auth_jwks_url="http://identity-api:8105/.well-known/jwks.json",
        database_url="postgresql+asyncpg://user:pass@db.example.com:5432/location",
        mapbox_api_key="mapbox-key",
        enable_ors_validation=True,
        ors_api_key="ors-key",
        ors_base_url="https://api.openrouteservice.org/v2/directions/driving-hgv",
        provider_timeout_ms=4000,
        provider_retry_max=2,
    )

    validate_prod_settings(candidate)
