from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import jwt
import pytest
import sqlalchemy as sa
from platform_auth import AuthSettings, verify_token
from ulid import ULID

from auth_service.config import settings
from auth_service.database import async_session_factory, engine
from auth_service.models import (
    Base,
    AuthOutboxModel,
    AuthSigningKeyModel,
    AuthWorkerHeartbeatModel,
)

from auth_service.token_service import (
    seed_bootstrap_state,
    validate_bootstrap_state,
)
from auth_service.workers.outbox_relay import OUTBOX_WORKER_NAME


def _new_ulid() -> str:
    return str(ULID())


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
    assert me_data["role"] == "USER"


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
        signing_key = await session.get(AuthSigningKeyModel, header["kid"])
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
async def test_register_flow(client) -> None:
    response = await client.post(
        "/auth/v1/register",
        json={
            "email": "newuser@example.com",
            "password": "new-password",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    
    async with async_session_factory() as session:
        result = await session.execute(
            sa.select(AuthOutboxModel).where(AuthOutboxModel.event_name == "user.registered")
        )
        row = result.scalar_one()
        payload = json.loads(row.payload_json)
        assert payload["email"] == "newuser@example.com"


@pytest.mark.asyncio
async def test_validate_bootstrap_state_requires_seeded_superadmin() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        with pytest.raises(RuntimeError, match="Bootstrap superadmin was not created."):
            await validate_bootstrap_state(session)

        await seed_bootstrap_state(session)
        await validate_bootstrap_state(session)


@pytest.mark.asyncio
async def test_health_and_ready_endpoints(client) -> None:
    health_response = await client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok", "service": "auth-service"}

    async with async_session_factory() as session:
        session.add(
            AuthWorkerHeartbeatModel(
                worker_name=OUTBOX_WORKER_NAME,
                last_seen_at_utc=datetime.now(UTC),
            )
        )
        await session.commit()

    ready_response = await client.get("/ready")
    assert ready_response.status_code == 200
    assert ready_response.json()["status"] == "ready"
    assert ready_response.json()["checks"] == {
        "database": "ok",
        "broker": "ok",
        "outbox_worker": "ok",
    }


@pytest.mark.asyncio
async def test_ready_requires_fresh_worker_heartbeat(client) -> None:
    async with async_session_factory() as session:
        session.add(
            AuthWorkerHeartbeatModel(
                worker_name=OUTBOX_WORKER_NAME,
                last_seen_at_utc=datetime.now(UTC)
                - timedelta(seconds=settings.outbox_worker_stale_after_seconds + 5),
            )
        )
        await session.commit()

    response = await client.get("/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["outbox_worker"] == "stale"


@pytest.mark.asyncio
async def test_ready_requires_broker_connectivity(client, monkeypatch) -> None:
    async with async_session_factory() as session:
        session.add(
            AuthWorkerHeartbeatModel(
                worker_name=OUTBOX_WORKER_NAME,
                last_seen_at_utc=datetime.now(UTC),
            )
        )
        await session.commit()

    async def broken_probe() -> tuple[bool, str | None]:
        return False, "broker down"

    monkeypatch.setattr(
        "auth_service.routers.health.probe_broker",
        broken_probe,
    )

    response = await client.get("/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["broker"] == "failed"
