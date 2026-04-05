from __future__ import annotations

import jwt
import pytest
from platform_auth import AuthSettings, verify_token

from identity_service.config import settings
from identity_service.database import async_session_factory
from identity_service.models import IdentitySigningKeyModel


@pytest.mark.asyncio
async def test_login_me_refresh_logout_flow(client) -> None:
    login_response = await client.post(
        "/auth/v1/login",
        json={"username": "bootstrap-admin", "password": "bootstrap-password"},
    )
    assert login_response.status_code == 200
    tokens = login_response.json()
    assert tokens["token_type"] == "bearer"

    me_response = await client.get(
        "/auth/v1/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert me_response.status_code == 200
    me_data = me_response.json()
    assert me_data["username"] == "bootstrap-admin"
    assert me_data["role"] == "SUPER_ADMIN"
    assert "SUPER_ADMIN" in me_data["groups"]

    refresh_response = await client.post(
        "/auth/v1/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh_response.status_code == 200
    refreshed = refresh_response.json()
    assert refreshed["access_token"] != tokens["access_token"]

    logout_response = await client.post(
        "/auth/v1/logout",
        json={"refresh_token": refreshed["refresh_token"]},
    )
    assert logout_response.status_code == 200
    assert logout_response.json()["status"] == "LOGGED_OUT"


@pytest.mark.asyncio
async def test_service_token_and_jwks_exposure(client) -> None:
    token_response = await client.post(
        "/auth/v1/token/service",
        json={
            "client_id": "trip-service",
            "client_secret": "trip-client-secret",
            "audience": settings.auth_audience,
        },
    )
    assert token_response.status_code == 200
    token = token_response.json()["access_token"]
    header = jwt.get_unverified_header(token)

    jwks_response = await client.get("/.well-known/jwks.json")
    assert jwks_response.status_code == 200
    keys = jwks_response.json()["keys"]
    assert any(item["kid"] == header["kid"] for item in keys)

    async with async_session_factory() as session:
        signing_key = await session.get(IdentitySigningKeyModel, header["kid"])
    assert signing_key is not None
    assert signing_key.private_key_ciphertext_b64
    assert signing_key.private_key_kek_version == "test-v1"
    claims = verify_token(
        token,
        AuthSettings(
            algorithm=settings.auth_jwt_algorithm,
            public_key=signing_key.public_key_pem,
            issuer=settings.auth_issuer,
            audience=settings.auth_audience,
        ),
    )
    assert claims.role == "SERVICE"
    assert claims.service == "trip-service"


@pytest.mark.asyncio
async def test_service_token_rejects_non_platform_audience(client) -> None:
    response = await client.post(
        "/auth/v1/token/service",
        json={
            "client_id": "trip-service",
            "client_secret": "trip-client-secret",
            "audience": "fleet-service",
        },
    )

    assert response.status_code in {400, 401}


@pytest.mark.asyncio
async def test_super_admin_can_create_and_update_user(client) -> None:
    login_response = await client.post(
        "/auth/v1/login",
        json={"username": "bootstrap-admin", "password": "bootstrap-password"},
    )
    access_token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    create_response = await client.post(
        "/admin/v1/users",
        json={
            "username": "manager-1",
            "email": "manager@example.com",
            "password": "manager-password",
            "groups": ["MANAGER"],
            "is_active": True,
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["username"] == "manager-1"
    assert created["groups"] == ["MANAGER"]

    update_response = await client.patch(
        f"/admin/v1/users/{created['user_id']}",
        json={"groups": ["ADMIN"], "is_active": False},
        headers=headers,
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["groups"] == ["ADMIN"]
    assert updated["is_active"] is False


@pytest.mark.asyncio
async def test_ready_endpoint(client) -> None:
    response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["checks"]["database"] == "ok"
    assert response.json()["checks"]["kek"] == "ok"
    assert response.json()["checks"]["bootstrap"] == "ok"
    assert response.json()["checks"]["signing_key"] == "ok"
