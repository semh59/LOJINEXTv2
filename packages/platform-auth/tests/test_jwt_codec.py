from __future__ import annotations

import json

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from platform_auth.dependencies import decode_bearer_token
from platform_auth.jwt_codec import issue_token, verify_token
from platform_auth.settings import AuthSettings
from platform_auth.token_factory import ServiceTokenFactory


def _rsa_keypair() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem


def test_hs256_service_token_factory_round_trip() -> None:
    settings = AuthSettings(
        algorithm="HS256",
        shared_secret="test-secret-at-least-32-bytes-long",
        issuer="lojinext-platform",
        audience="trip-service",
    )
    factory = ServiceTokenFactory(service_name="driver-service", settings=settings)
    token = factory.issue()

    claims = verify_token(token, settings)

    assert claims.sub == "driver-service"
    assert claims.role == "SERVICE"
    assert claims.service == "driver-service"
    assert claims.iss == "lojinext-platform"
    assert claims.aud == ("trip-service",)
    assert claims.jti is not None


def test_rs256_issue_and_verify_with_direct_keys() -> None:
    private_key, public_key = _rsa_keypair()
    settings = AuthSettings(
        algorithm="RS256",
        private_key=private_key,
        public_key=public_key,
        issuer="lojinext-platform",
        audience="identity-tests",
    )
    token = issue_token(
        {
            "sub": "admin-1",
            "role": "SUPER_ADMIN",
            "iss": "lojinext-platform",
            "aud": "identity-tests",
        },
        settings,
        headers={"kid": "key-1"},
    )

    claims = decode_bearer_token(f"Bearer {token}", settings)

    assert claims.sub == "admin-1"
    assert claims.role == "SUPER_ADMIN"
    assert claims.kid == "key-1"


def test_jwks_cache_provider_reuses_cached_key(monkeypatch) -> None:
    private_key, public_key = _rsa_keypair()
    signing_settings = AuthSettings(
        algorithm="RS256",
        private_key=private_key,
        public_key=public_key,
        issuer="lojinext-platform",
        audience="fleet-service",
    )
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(serialization.load_pem_public_key(public_key.encode("utf-8"))))
    jwk["kid"] = "active-key"
    token = issue_token(
        {
            "sub": "trip-service",
            "role": "SERVICE",
            "service": "trip-service",
            "iss": "lojinext-platform",
            "aud": "fleet-service",
        },
        signing_settings,
        headers={"kid": "active-key"},
    )

    calls = {"count": 0}

    class _MockResponse:
        def __enter__(self) -> "_MockResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
            return None

        def read(self) -> bytes:
            return json.dumps({"keys": [jwk]}).encode("utf-8")

    def _mock_urlopen(request, timeout=5):  # noqa: ANN001, ARG001
        calls["count"] += 1
        return _MockResponse()

    monkeypatch.setattr("urllib.request.urlopen", _mock_urlopen)
    verify_settings = AuthSettings(
        algorithm="RS256",
        jwks_url="https://identity.local/.well-known/jwks.json",
        issuer="lojinext-platform",
        audience="fleet-service",
        jwks_cache_ttl_seconds=300,
    )

    first = verify_token(token, verify_settings)
    second = verify_token(token, verify_settings)

    assert first.service == "trip-service"
    assert second.service == "trip-service"
    assert calls["count"] == 1
