"""System-wide identity constants."""

from platform_auth import PlatformRole

ROLE_PRIORITY = {
    str(PlatformRole.SUPER_ADMIN): 3,
    str(PlatformRole.MANAGER): 2,
    str(PlatformRole.OPERATOR): 1,
}

USER_ROLE_NAMES = set(ROLE_PRIORITY)

# Core Permissions
PERMISSION_USERS_READ = "identity:users:read"
PERMISSION_USERS_WRITE = "identity:users:write"
PERMISSION_GROUPS_MANAGE = "identity:groups:manage"
PERMISSION_AUDIT_READ = "identity:audit:read"

ALL_CORE_PERMISSIONS = [
    PERMISSION_USERS_READ,
    PERMISSION_USERS_WRITE,
    PERMISSION_GROUPS_MANAGE,
    PERMISSION_AUDIT_READ,
]
