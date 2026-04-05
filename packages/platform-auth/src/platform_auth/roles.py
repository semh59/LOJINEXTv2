"""Shared role vocabulary."""

from enum import StrEnum


class PlatformRole(StrEnum):
    """Cross-service authorization roles."""

    SUPER_ADMIN = "SUPER_ADMIN"
    MANAGER = "MANAGER"
    OPERATOR = "OPERATOR"
    SERVICE = "SERVICE"


class PlatformActorType(StrEnum):
    """Standardized actor types for audit logs and events."""

    SYSTEM = "SYSTEM"
    SERVICE = "SERVICE"
    USER = "USER"
    DRIVER = "DRIVER"
