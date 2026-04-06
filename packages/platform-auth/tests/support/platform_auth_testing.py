"""Shared RS256/JWKS test helpers for service suites."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


DEFAULT_TEST_JWKS_URL = "https://identity.test/.well-known/jwks.json"


@dataclass(frozen=True)
class TestJwksBundle:
    """RSA key material and JWKS payload used by tests."""

    kid: str
    issuer: str
    audience: str
    jwks_url: str
    private_key_pem: str
    public_key_pem: str
    jwk: dict[str, Any]
    jwks: dict[str, Any]


class _MockHttpResponse:
    """Minimal urllib response object for JWKS mocking."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.status = 200
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_MockHttpResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        del exc_type, exc, tb
        return None


def build_test_jwks_bundle(
    *,
    kid: str = "test-key",
    issuer: str = "lojinext-platform",
    audience: str = "lojinext-platform",
) -> TestJwksBundle:
    """Return a self-contained RSA keypair plus JWKS document."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_key_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public_key))
    jwk["kid"] = kid
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    jwks = {"keys": [jwk]}

    return TestJwksBundle(
        kid=kid,
        issuer=issuer,
        audience=audience,
        jwks_url=DEFAULT_TEST_JWKS_URL,
        private_key_pem=private_key_pem,
        public_key_pem=public_key_pem,
        jwk=jwk,
        jwks=jwks,
    )


def install_jwks_urlopen_mock(
    monkeypatch,  # noqa: ANN001
    bundle: TestJwksBundle,
    *,
    jwks_url: str = DEFAULT_TEST_JWKS_URL,
) -> None:
    """Monkeypatch urllib JWKS fetches to return the bundle payload."""
    from platform_auth import key_provider

    key_provider._JWKS_PROVIDER_CACHE.clear()

    def _mock_urlopen(request, timeout=5):  # noqa: ANN001
        del timeout
        requested_url = request.full_url if isinstance(request, urllib.request.Request) else str(request)
        if requested_url != jwks_url:
            raise urllib.error.URLError(f"Unexpected JWKS URL: {requested_url}")
        return _MockHttpResponse(bundle.jwks)

    monkeypatch.setattr(urllib.request, "urlopen", _mock_urlopen)


def sign_test_token(
    bundle: TestJwksBundle,
    *,
    sub: str,
    role: str,
    service: str | None = None,
    aud: str | None = None,
    iss: str | None = None,
    expires_in_seconds: int = 300,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Issue an RS256 test token matching the shared JWKS bundle."""
    issued_at = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": sub,
        "role": role,
        "iss": iss or bundle.issuer,
        "aud": aud or bundle.audience,
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + timedelta(seconds=expires_in_seconds)).timestamp()),
    }
    if service is not None:
        payload["service"] = service
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(
        payload,
        bundle.private_key_pem,
        algorithm="RS256",
        headers={"kid": bundle.kid},
    )
