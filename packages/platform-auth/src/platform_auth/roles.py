"""Shared role vocabulary."""

from enum import StrEnum


class PlatformRole(StrEnum):
    """Cross-service actor roles supported by the platform."""

    ADMIN = "ADMIN"
    SUPER_ADMIN = "SUPER_ADMIN"
    MANAGER = "MANAGER"
    SERVICE = "SERVICE"
