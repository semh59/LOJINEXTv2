from __future__ import annotations

import pytest

from location_service.config import DEFAULT_AUTH_JWT_SECRET, DEFAULT_DATABASE_URL, settings, validate_prod_settings


def _candidate(**overrides: object):
    base = settings.model_copy(deep=True)
    return base.model_copy(update=overrides)


def test_prod_validation_rejects_default_jwt_secret() -> None:
    candidate = _candidate(
        environment="prod",
        auth_jwt_secret=DEFAULT_AUTH_JWT_SECRET,
        database_url="postgresql+asyncpg://user:pass@db.example.com:5432/location",
        mapbox_api_key="mapbox-key",
        enable_ors_validation=False,
    )

    with pytest.raises(ValueError, match="LOCATION_AUTH_JWT_SECRET"):
        validate_prod_settings(candidate)


def test_prod_validation_rejects_default_database_url() -> None:
    candidate = _candidate(
        environment="prod",
        auth_jwt_secret="prod-secret-12345678901234567890",
        database_url=DEFAULT_DATABASE_URL,
        mapbox_api_key="mapbox-key",
        enable_ors_validation=False,
    )

    with pytest.raises(ValueError, match="LOCATION_DATABASE_URL"):
        validate_prod_settings(candidate)


def test_prod_validation_requires_mapbox_key() -> None:
    candidate = _candidate(
        environment="prod",
        auth_jwt_secret="prod-secret-12345678901234567890",
        database_url="postgresql+asyncpg://user:pass@db.example.com:5432/location",
        mapbox_api_key="",
        enable_ors_validation=False,
    )

    with pytest.raises(ValueError, match="LOCATION_MAPBOX_API_KEY"):
        validate_prod_settings(candidate)


def test_prod_validation_requires_ors_settings_when_enabled() -> None:
    candidate = _candidate(
        environment="prod",
        auth_jwt_secret="prod-secret-12345678901234567890",
        database_url="postgresql+asyncpg://user:pass@db.example.com:5432/location",
        mapbox_api_key="mapbox-key",
        enable_ors_validation=True,
        ors_api_key="",
        ors_base_url="",
    )

    with pytest.raises(ValueError, match="LOCATION_ORS_API_KEY"):
        validate_prod_settings(candidate)


def test_prod_validation_accepts_complete_config() -> None:
    candidate = _candidate(
        environment="prod",
        auth_jwt_secret="prod-secret-12345678901234567890",
        database_url="postgresql+asyncpg://user:pass@db.example.com:5432/location",
        mapbox_api_key="mapbox-key",
        enable_ors_validation=True,
        ors_api_key="ors-key",
        ors_base_url="https://api.openrouteservice.org/v2/directions/driving-hgv",
        provider_timeout_ms=4000,
        provider_retry_max=2,
    )

    validate_prod_settings(candidate)
