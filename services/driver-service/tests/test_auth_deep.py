"""Deep testing for Driver Service RS256 Authentication (V2.1)."""

import jwt
import pytest
from httpx import AsyncClient
from platform_auth_testing import build_test_jwks_bundle, sign_test_token

from driver_service.config import settings


@pytest.mark.asyncio
async def test_auth_rs256_happy_path(client: AsyncClient):
    """Verify that a properly signed RS256 token is accepted."""
    from conftest import TEST_JWKS_BUNDLE

    token = sign_test_token(TEST_JWKS_BUNDLE, sub="admin-user", role="ADMIN")

    resp = await client.get("/api/v1/drivers", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auth_rs256_expired_token(client: AsyncClient):
    """Verify that an expired token is rejected with 401."""
    from conftest import TEST_JWKS_BUNDLE

    # Sign a token that expired (using negative expires_in_seconds)
    token = sign_test_token(TEST_JWKS_BUNDLE, sub="expired-user", role="ADMIN", expires_in_seconds=-3600)

    resp = await client.get("/api/v1/drivers", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert "Signature has expired" in resp.text


@pytest.mark.asyncio
async def test_auth_rs256_invalid_issuer(client: AsyncClient):
    """Verify that a token with an unknown issuer is rejected."""
    from conftest import TEST_JWKS_BUNDLE

    token = sign_test_token(TEST_JWKS_BUNDLE, sub="user", role="ADMIN", iss="http://malicious-issuer.com")

    resp = await client.get("/api/v1/drivers", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert "Invalid issuer" in resp.text


@pytest.mark.asyncio
async def test_auth_rs256_wrong_key(client: AsyncClient):
    """Verify that a token signed by a different key is rejected."""
    malicious_bundle = build_test_jwks_bundle(issuer=settings.auth_issuer)

    token = sign_test_token(malicious_bundle, sub="hacker", role="ADMIN")

    resp = await client.get("/api/v1/drivers", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_rs256_insufficient_role(client: AsyncClient):
    """Verify that a valid token with wrong role gets 403."""
    from conftest import TEST_JWKS_BUNDLE

    token = sign_test_token(TEST_JWKS_BUNDLE, sub="normal-user", role="GUEST")

    resp = await client.get("/api/v1/drivers", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_auth_alg_none_attack(client: AsyncClient):
    """Verify that 'alg: none' tokens are rejected."""
    payload = {
        "sub": "hacker",
        "role": "ADMIN",
        "iss": settings.auth_issuer,
        "aud": settings.auth_audience,
    }
    # Create token with alg: None
    token = jwt.encode(payload, key="", algorithm=None)

    resp = await client.get("/api/v1/drivers", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_hs256_substitution_attack(client: AsyncClient):
    """Verify that using a symmetric key (HS256) where RS256 is expected is rejected."""
    import base64
    import hashlib
    import hmac
    import json

    from conftest import TEST_JWKS_BUNDLE

    header = {"alg": "HS256", "typ": "JWT", "kid": TEST_JWKS_BUNDLE.kid}
    payload = {
        "sub": "hacker",
        "role": "ADMIN",
        "iss": settings.auth_issuer,
        "aud": settings.auth_audience,
    }

    def b64_json(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=")

    segments = [b64_json(header), b64_json(payload)]
    signing_input = b".".join(segments)

    # Use HMAC manual signing with the public key as secret
    key = TEST_JWKS_BUNDLE.public_key_pem.encode()
    signature = hmac.new(key, signing_input, hashlib.sha256).digest()
    token = signing_input.decode() + "." + base64.urlsafe_b64encode(signature).decode().rstrip("=")

    resp = await client.get("/api/v1/drivers", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
