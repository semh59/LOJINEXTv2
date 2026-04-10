from __future__ import annotations

from dataclasses import dataclass

from platform_auth.roles import PlatformActorType, PlatformRole


@dataclass(frozen=True)
class AuthContext:
    """Authenticated caller context used by routers across all services."""

    actor_id: str
    role: str
    actor_type: str | None = None
    service_name: str | None = None

    def __post_init__(self) -> None:
        if self.actor_type is None:
            object.__setattr__(self, "actor_type", self.role)

    @property
    def is_super_admin(self) -> bool:
        return self.role == PlatformRole.SUPER_ADMIN

    @property
    def is_admin(self) -> bool:
        return self.role == PlatformRole.SUPER_ADMIN

    @property
    def is_manager(self) -> bool:
        return self.role == PlatformRole.MANAGER

    @property
    def is_service(self) -> bool:
        return self.role == PlatformRole.SERVICE

    @property
    def is_internal_service(self) -> bool:
        return self.role == PlatformRole.SERVICE
