from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
import sqlalchemy as sa
from platform_auth import AuthSettings, PlatformRole, verify_token
from ulid import ULID

from identity_service.config import settings
from identity_service.database import async_session_factory, engine
from identity_service.models import (
    Base,
    IdentityAuditLogModel,
    IdentityGroupModel,
    IdentityOutboxModel,
    IdentitySigningKeyModel,
    IdentityUserGroupModel,
    IdentityUserModel,
    IdentityWorkerHeartbeatModel,
)
from identity_service.password import hash_secret
from identity_service.token_service import (
    seed_bootstrap_state,
    validate_bootstrap_state,
)
from identity_service.workers.outbox_relay import OUTBOX_WORKER_NAME


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
    me_response = await client.get(
        "/auth/v1/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    admin_user_id = me_response.json()["user_id"]

    create_response = await client.post(
        "/admin/v1/users",
        json={
            "username": "manager-1",
            "email": "manager@example.com",
            "password": "manager-password",
            "groups": ["MANAGER"],
            "is_active": True,
        },
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Correlation-ID": "req-create-1",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["username"] == "manager-1"
    assert created["groups"] == ["MANAGER"]

    update_response = await client.patch(
        f"/admin/v1/users/{created['user_id']}",
        json={"groups": ["OPERATOR"], "is_active": False},
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Correlation-ID": "req-update-1",
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["groups"] == ["OPERATOR"]
    assert updated["is_active"] is False

    async with async_session_factory() as session:
        audits = (
            (
                await session.execute(
                    sa.select(IdentityAuditLogModel)
                    .order_by(IdentityAuditLogModel.created_at_utc.asc())
                    .where(IdentityAuditLogModel.target_id == created["user_id"])
                )
            )
            .scalars()
            .all()
        )
        outbox_rows = (
            (
                await session.execute(
                    sa.select(IdentityOutboxModel).order_by(
                        IdentityOutboxModel.created_at_utc.asc()
                    )
                )
            )
            .scalars()
            .all()
        )

    assert [audit.action_type for audit in audits] == ["CREATE", "UPDATE"]
    assert [audit.actor_id for audit in audits] == [admin_user_id, admin_user_id]
    assert [audit.request_id for audit in audits] == ["req-create-1", "req-update-1"]
    assert sorted(row.event_name for row in outbox_rows) == [
        "identity.user.created.v1",
        "identity.user.groups_assigned.v1",
        "identity.user.groups_assigned.v1",
        "identity.user.updated.v1",
    ]


@pytest.mark.asyncio
async def test_admin_rejects_non_canonical_groups(client) -> None:
    login_response = await client.post(
        "/auth/v1/login",
        json={"username": "bootstrap-admin", "password": "bootstrap-password"},
    )
    access_token = login_response.json()["access_token"]

    response = await client.post(
        "/admin/v1/users",
        json={
            "username": "bad-group-user",
            "email": "bad-group@example.com",
            "password": "bad-group-password",
            "groups": ["ADMIN"],
            "is_active": True,
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_rejects_user_with_service_group_assignment(client) -> None:
    async with async_session_factory() as session:
        service_group = IdentityGroupModel(
            group_id=_new_ulid(),
            group_name=str(PlatformRole.SERVICE),
            description="Invalid human assignment",
        )
        user = IdentityUserModel(
            user_id=_new_ulid(),
            username="invalid-service-user",
            email="invalid-service@example.com",
            password_hash=hash_secret("service-password"),
            is_active=True,
            created_at_utc=datetime.now(UTC),
            updated_at_utc=datetime.now(UTC),
        )
        session.add(service_group)
        session.add(user)
        await session.flush()
        session.add(
            IdentityUserGroupModel(
                user_id=user.user_id,
                group_id=service_group.group_id,
                assigned_at=datetime.now(UTC),
            )
        )
        await session.commit()

    response = await client.post(
        "/auth/v1/login",
        json={"username": "invalid-service-user", "password": "service-password"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "User role assignments invalid."


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
    assert health_response.json() == {"status": "ok"}

    async with async_session_factory() as session:
        session.add(
            IdentityWorkerHeartbeatModel(
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
            IdentityWorkerHeartbeatModel(
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
            IdentityWorkerHeartbeatModel(
                worker_name=OUTBOX_WORKER_NAME,
                last_seen_at_utc=datetime.now(UTC),
            )
        )
        await session.commit()

    async def broken_probe() -> tuple[bool, str | None]:
        return False, "broker down"

    monkeypatch.setattr(
        "identity_service.routers.health.probe_broker",
        broken_probe,
    )

    response = await client.get("/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["broker"] == "failed"
