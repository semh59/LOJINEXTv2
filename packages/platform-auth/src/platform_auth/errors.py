"""Platform auth error types."""


class PlatformAuthError(Exception):
    """Base class for auth-layer failures."""


class TokenMissingError(PlatformAuthError):
    """Authorization input was missing."""


class TokenInvalidError(PlatformAuthError):
    """JWT was malformed, expired, or could not be verified."""


class TokenForbiddenError(PlatformAuthError):
    """Caller is authenticated but not authorized."""


class KeyResolutionError(PlatformAuthError):
    """Signing or verification key could not be resolved."""
