"""Identity Service configuration."""

import os
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings

DEFAULT_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/identity_service"


class Settings(BaseSettings):
    """Identity Service configuration loaded from environment variables."""

    service_name: str = "identity-service"
    service_port: int = 8105
    environment: Literal["dev", "test", "prod"] = "dev"
    database_url: str = DEFAULT_DATABASE_URL

    auth_jwt_algorithm: str = "RS256"
    auth_issuer: str = "lojinext-platform"
    auth_audience: str = "lojinext-platform"
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 60 * 60 * 24 * 14
    service_token_ttl_seconds: int = 300

    bootstrap_superadmin_username: str = "superadmin"
    bootstrap_superadmin_email: str = "superadmin@example.com"
    bootstrap_superadmin_password: str = "change-me-now"
    bootstrap_service_clients: str = Field(default="", validation_alias="IDENTITY_SERVICE_CLIENTS")
    bootstrap_service_clients_json: str = ""
    key_encryption_key_b64: str = ""
    key_encryption_key_version: str = ""

    model_config = {"env_prefix": "IDENTITY_", "env_file": ".env", "extra": "ignore"}

    @property
    def bootstrap_service_names(self) -> list[str]:
        """Return the configured bootstrap service client names."""
        return [item.strip() for item in self.bootstrap_service_clients.split(",") if item.strip()]

    @staticmethod
    def service_client_secret_env_name(service_name: str) -> str:
        """Return the canonical env var name for a service client secret."""
        normalized = service_name.strip().upper().replace("-", "_")
        return f"IDENTITY_SERVICE_CLIENT_SECRET__{normalized}"

    def service_client_secret(self, service_name: str) -> str:
        """Return the bootstrap secret for a named service client."""
        return os.getenv(self.service_client_secret_env_name(service_name), "").strip()


settings = Settings()


def validate_prod_settings(current: Settings) -> None:
    """Fail fast when production settings are incomplete."""
    if current.environment != "prod":
        return

    errors: list[str] = []
    if current.auth_jwt_algorithm.upper() != "RS256":
        errors.append("IDENTITY_AUTH_JWT_ALGORITHM must be RS256 in prod.")
    if not current.database_url or current.database_url == DEFAULT_DATABASE_URL:
        errors.append("IDENTITY_DATABASE_URL must be set to a non-default value in prod.")
    if not current.auth_issuer:
        errors.append("IDENTITY_AUTH_ISSUER must be set in prod.")
    if not current.auth_audience:
        errors.append("IDENTITY_AUTH_AUDIENCE must be set in prod.")
    if current.bootstrap_superadmin_password == "change-me-now":
        errors.append("IDENTITY_BOOTSTRAP_SUPERADMIN_PASSWORD must be overridden in prod.")
    if not current.key_encryption_key_b64:
        errors.append("IDENTITY_KEY_ENCRYPTION_KEY_B64 must be set in prod.")
    if not current.key_encryption_key_version:
        errors.append("IDENTITY_KEY_ENCRYPTION_KEY_VERSION must be set in prod.")
    if current.bootstrap_service_clients_json:
        errors.append("IDENTITY_BOOTSTRAP_SERVICE_CLIENTS_JSON is not allowed in prod.")
    if not current.bootstrap_service_names:
        errors.append("IDENTITY_SERVICE_CLIENTS must list bootstrap service clients in prod.")
    for service_name in current.bootstrap_service_names:
        if not current.service_client_secret(service_name):
            errors.append(
                f"{current.service_client_secret_env_name(service_name)} must be set for bootstrap service clients."
            )

    if errors:
        raise ValueError("Production settings invalid: " + " ".join(errors))
