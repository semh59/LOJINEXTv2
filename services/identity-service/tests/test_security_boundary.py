"""Security boundary tests for identity-service."""

from __future__ import annotations

import asyncio
import base64
import json
import jwt
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity_service.models import (
    IdentityAuditLogModel,
    IdentitySigningKeyModel,
    IdentityUserModel,
)
from identity_service.token_service import (
    decode_access_token,
    issue_token_pair,
    now_utc,
    seed_bootstrap_state,
    serialize_user,
    write_audit,
)


# ---------------------------------------------------------------------------
# Existing tests (retained)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_masking_integrity(session: AsyncSession):
    """Scan audit snapshots for unmasked emails to ensure forensic airtightness."""
    await seed_bootstrap_state(session)
    user = (await session.execute(select(IdentityUserModel).limit(1))).scalar_one()

    await write_audit(
        session,
        "USER",
        user.user_id,
        "UPDATE",
        "ADMIN",
        "SUPER_ADMIN",
        new_snapshot=serialize_user(user, mask_pii=True),
    )
    await session.commit()

    result = await session.execute(select(IdentityAuditLogModel))
    logs = result.scalars().all()

    for log in logs:
        if log.new_snapshot_json:
            assert user.email not in log.new_snapshot_json, (
                f"PII Leak detected in audit snapshot! ID: {log.audit_id}"
            )


@pytest.mark.asyncio
async def test_security_jwt_integrity(session: AsyncSession):
    """Verify that RS256 signature mutation is detected and rejected."""
    await seed_bootstrap_state(session)
    user = (await session.execute(select(IdentityUserModel).limit(1))).scalar_one()

    token_pair = await issue_token_pair(session, user)
    token = token_pair["access_token"]

    header, payload, signature = token.split(".")
    pad = "=" * (4 - len(payload) % 4)
    payload_dict = json.loads(base64.urlsafe_b64decode(payload + pad))
    payload_dict["role"] = "ULTIMATE_HACKER"
    mutated_payload = (
        base64.urlsafe_b64encode(json.dumps(payload_dict).encode()).decode().rstrip("=")
    )
    mutated_token = f"{header}.{mutated_payload}.{signature}"

    with pytest.raises(Exception):
        await decode_access_token(session, mutated_token)


# ---------------------------------------------------------------------------
# NEW: BUG-4 — Audience bypass is fixed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audience_bypass_rejected_without_strict_mode(client) -> None:
    """Service-A cannot request a token for audience=service-B when strict=False (default)."""
    response = await client.post(
        "/auth/v1/token/service",
        json={
            "client_id": "trip-service",
            "client_secret": "trip-client-secret",
            "audience": "fleet-service",  # different service, not platform audience
        },
    )
    # Must be rejected — default strict=False means cross-audience is disabled
    assert response.status_code in {400, 401}
    body = response.json()
    assert "error_code" in body  # platform-standard error format
    assert "disabled" in body["message"].lower() or "audience" in body["message"].lower()


# ---------------------------------------------------------------------------
# NEW: BUG-5 — Retired signing key rejected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retired_signing_key_rejects_decode(session: AsyncSession) -> None:
    """A token signed with a now-retired key must be rejected on decode."""
    user = (await session.execute(select(IdentityUserModel).limit(1))).scalar_one()
    token_pair = await issue_token_pair(session, user)
    access_token = token_pair["access_token"]

    # Extract kid from token header
    kid = jwt.get_unverified_header(access_token)["kid"]

    # Retire the signing key
    signing_key = await session.get(IdentitySigningKeyModel, kid)
    assert signing_key is not None
    signing_key.retired_at_utc = now_utc()
    await session.commit()

    # Decode attempt must fail
    async with __import__("identity_service.database", fromlist=["async_session_factory"]).async_session_factory() as new_session:
        with pytest.raises(ValueError, match="retired"):
            await decode_access_token(new_session, access_token)


# ---------------------------------------------------------------------------
# NEW: BUG-2 — Refresh token family reuse detection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refresh_token_reuse_invalidates_family(client) -> None:
    """Reusing a revoked refresh token must invalidate all tokens in its family."""
    # Login to get initial token pair
    login = await client.post(
        "/auth/v1/login",
        json={"username": "bootstrap-admin", "password": "bootstrap-password"},
    )
    assert login.status_code == 200
    tokens = login.json()
    original_refresh = tokens["refresh_token"]

    # Rotate once to get a new pair (this revokes original_refresh)
    rotate = await client.post(
        "/auth/v1/refresh",
        json={"refresh_token": original_refresh},
    )
    assert rotate.status_code == 200
    rotated = rotate.json()

    # Attempt to reuse the original (revoked) refresh token
    reuse = await client.post(
        "/auth/v1/refresh",
        json={"refresh_token": original_refresh},
    )
    assert reuse.status_code == 401
    assert "reuse" in reuse.json()["message"].lower() or "invalidated" in reuse.json()["message"].lower()

    # The rotated token must also now be invalid (family was nuked)
    after_nuke = await client.post(
        "/auth/v1/refresh",
        json={"refresh_token": rotated["refresh_token"]},
    )
    assert after_nuke.status_code == 401


# ---------------------------------------------------------------------------
# NEW: H-4 — Logout blocklists access token
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_logout_blocklists_access_token(client) -> None:
    """After logout with Authorization header, the access token must be rejected."""
    login = await client.post(
        "/auth/v1/login",
        json={"username": "bootstrap-admin", "password": "bootstrap-password"},
    )
    assert login.status_code == 200
    tokens = login.json()
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    # Verify token works before logout
    me_before = await client.get(
        "/auth/v1/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_before.status_code == 200

    # Logout with access token in header
    logout = await client.post(
        "/auth/v1/logout",
        json={"refresh_token": refresh_token},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert logout.status_code == 200

    # Same access token must now be rejected
    me_after = await client.get(
        "/auth/v1/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_after.status_code == 401


# ---------------------------------------------------------------------------
# NEW: H-4 — User deactivation revokes refresh tokens
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_user_deactivation_revokes_refresh_tokens(client) -> None:
    """Deactivating a user must revoke all their active refresh tokens."""
    # Login as admin
    admin_login = await client.post(
        "/auth/v1/login",
        json={"username": "bootstrap-admin", "password": "bootstrap-password"},
    )
    admin_token = admin_login.json()["access_token"]

    # Create a test user
    create = await client.post(
        "/admin/v1/users",
        json={
            "username": "test-deactivate",
            "email": "deactivate@example.com",
            "password": "deactivate-password",
            "groups": ["OPERATOR"],
            "is_active": True,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert create.status_code == 201
    user_id = create.json()["user_id"]

    # Log in as the test user
    user_login = await client.post(
        "/auth/v1/login",
        json={"username": "test-deactivate", "password": "deactivate-password"},
    )
    assert user_login.status_code == 200
    user_refresh = user_login.json()["refresh_token"]

    # Deactivate the user
    deactivate = await client.patch(
        f"/admin/v1/users/{user_id}",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert deactivate.status_code == 200
    assert deactivate.json()["is_active"] is False

    # Refresh attempt with the user's token must fail
    refresh_attempt = await client.post(
        "/auth/v1/refresh",
        json={"refresh_token": user_refresh},
    )
    assert refresh_attempt.status_code == 401


# ---------------------------------------------------------------------------
# NEW: BUG-1 — Rate limiting on login endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rate_limit_login_by_ip(client) -> None:
    """Exceeding per-IP rate limit on login returns 429."""
    from identity_service.config import settings

    limit = settings.rate_limit_login_per_minute

    # Send limit+1 requests — the last one should be 429
    responses = []
    for _ in range(limit + 1):
        r = await client.post(
            "/auth/v1/login",
            json={"username": "nonexistent", "password": "wrongpassword"},
        )
        responses.append(r.status_code)

    assert 429 in responses, f"Expected a 429 among: {responses}"
    # First `limit` requests should be 401 (wrong creds), not 429
    assert responses[0] == 401


@pytest.mark.asyncio
async def test_login_lockout_after_repeated_failures(client) -> None:
    """Correct credentials are blocked after repeated failures for the same username."""
    from identity_service.config import settings

    failures = settings.rate_limit_login_failures_before_lockout

    # Exhaust failure allowance
    for _ in range(failures):
        r = await client.post(
            "/auth/v1/login",
            json={"username": "bootstrap-admin", "password": "wrong-password"},
        )
        # Each failure should be 401 (until lockout kicks in)
        assert r.status_code in {401, 429}

    # Now correct credentials must be locked out
    locked = await client.post(
        "/auth/v1/login",
        json={"username": "bootstrap-admin", "password": "bootstrap-password"},
    )
    assert locked.status_code == 429
    assert "locked" in locked.json()["message"].lower() or "locked" in locked.json()["error_code"].lower()


# ---------------------------------------------------------------------------
# NEW: Outbox worker shutdown_event
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_outbox_worker_respects_shutdown_event() -> None:
    """Outbox relay exits promptly when shutdown_event is set."""
    from identity_service.broker import create_broker
    from identity_service.workers.outbox_relay import run_outbox_relay

    broker = create_broker("noop")
    shutdown_event = asyncio.Event()

    # Signal shutdown immediately
    shutdown_event.set()

    # Worker should return without blocking
    await asyncio.wait_for(
        run_outbox_relay(broker, shutdown_event=shutdown_event),
        timeout=2.0,
    )
    await broker.close()
