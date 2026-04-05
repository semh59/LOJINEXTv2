"""Decoded JWT claim models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


def _as_str_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str) and value:
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value if str(item).strip())
    return ()


@dataclass(frozen=True)
class TokenClaims:
    """Normalized JWT claims used by service adapters."""

    sub: str
    role: str
    service: str | None = None
    iss: str | None = None
    aud: tuple[str, ...] = ()
    iat: int | None = None
    exp: int | None = None
    jti: str | None = None
    kid: str | None = None
    groups: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, Any],
        *,
        header: Mapping[str, Any] | None = None,
    ) -> "TokenClaims":
        """Build normalized claims from a raw JWT payload."""
        sub = str(payload.get("sub", "")).strip()
        role = str(payload.get("role", "")).strip()
        service = str(payload.get("service", "")).strip() or None
        iss = str(payload.get("iss", "")).strip() or None
        jti = str(payload.get("jti", "")).strip() or None
        kid = None
        if header is not None:
            kid = str(header.get("kid", "")).strip() or None
        iat = int(payload["iat"]) if "iat" in payload and payload["iat"] is not None else None
        exp = int(payload["exp"]) if "exp" in payload and payload["exp"] is not None else None
        return cls(
            sub=sub,
            role=role,
            service=service,
            iss=iss,
            aud=_as_str_tuple(payload.get("aud")),
            iat=iat,
            exp=exp,
            jti=jti,
            kid=kid,
            groups=_as_str_tuple(payload.get("groups")),
            permissions=_as_str_tuple(payload.get("permissions")),
            raw=dict(payload),
        )

    @property
    def is_service(self) -> bool:
        """Return whether claims represent a service principal."""
        return self.role == "SERVICE"
