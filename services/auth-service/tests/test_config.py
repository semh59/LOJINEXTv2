from __future__ import annotations

import pytest

from auth_service.config import Settings, validate_prod_settings


def test_service_client_secret_env_name_normalizes_dashes() -> None:
    assert (
        Settings.service_client_secret_env_name("trip-service")
        == "AUTH_SERVICE_CLIENT_SECRET__TRIP_SERVICE"
    )
    assert (
        Settings.service_client_secret_env_name("fleet-service")
        == "AUTH_SERVICE_CLIENT_SECRET__FLEET_SERVICE"
    )


def test_validate_prod_settings_rejects_json_bootstrap() -> None:
    settings = Settings(
        environment="prod",
        database_url="postgresql+asyncpg://identity:identity@db:5432/auth_service",
        auth_jwt_algorithm="RS256",
        auth_issuer="lojinext-platform",
        auth_audience="lojinext-platform",
        bootstrap_superadmin_password="strong-password",
        bootstrap_service_clients="trip-service",
        bootstrap_service_clients_json='[{"client_id":"trip-service"}]',
        key_encryption_key_b64="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        key_encryption_key_version="prod-v1",
    )

    with pytest.raises(
        ValueError,
        match="AUTH_BOOTSTRAP_SERVICE_CLIENTS_JSON is not allowed in prod.",
    ):
        validate_prod_settings(settings)
