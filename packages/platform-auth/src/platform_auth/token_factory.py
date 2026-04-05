"""Token issuance helpers."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from platform_auth.jwt_codec import issue_token
from platform_auth.roles import PlatformRole
from platform_auth.settings import AuthSettings


@dataclass(frozen=True)
class ServiceTokenFactory:
    """Issue short-lived service-to-service JWTs."""

    service_name: str
    settings: AuthSettings
    ttl_seconds: int = 300

    def build_payload(
        self,
        *,
        audience: str | None = None,
        additional_claims: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a normalized service-token payload."""
        now = int(time.time())
        payload: dict[str, Any] = {
            "sub": self.service_name,
            "role": PlatformRole.SERVICE,
            "service": self.service_name,
            "iat": now,
            "exp": now + self.ttl_seconds,
            "jti": uuid4().hex,
        }
        if self.settings.issuer:
            payload["iss"] = self.settings.issuer
        effective_audience = audience or self.settings.audience
        if effective_audience:
            payload["aud"] = effective_audience
        if additional_claims:
            payload.update(additional_claims)
        return payload

    def issue(
        self,
        *,
        audience: str | None = None,
        additional_claims: dict[str, Any] | None = None,
        kid: str | None = None,
    ) -> str:
        """Issue a service token."""
        headers = {"kid": kid} if kid else None
        payload = self.build_payload(audience=audience, additional_claims=additional_claims)
        return issue_token(payload, self.settings, headers=headers)

    def auth_header(
        self,
        *,
        audience: str | None = None,
        additional_claims: dict[str, Any] | None = None,
        kid: str | None = None,
    ) -> dict[str, str]:
        """Return an Authorization header containing a service token."""
        return {
            "Authorization": f"Bearer {self.issue(audience=audience, additional_claims=additional_claims, kid=kid)}"
        }
