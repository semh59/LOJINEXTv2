"""Core token and bootstrap services."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from datetime import UTC, date, datetime, timedelta
from functools import partial
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import jwt
from platform_auth import AuthSettings, PlatformRole, verify_token
from platform_auth.jwt_codec import issue_token
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from identity_service.config import settings
from identity_service.constants import (
    ALL_CORE_PERMISSIONS,
    ROLE_PRIORITY,
    USER_ROLE_NAMES,
)
from identity_service.crypto import (
    decrypt_private_key,
    encrypt_private_key,
    require_kek_version,
)
from identity_service.jwks import generate_rsa_keypair, public_key_to_jwk
from identity_service.models import (
    IdentityAuditLogModel,
    IdentityGroupModel,
    IdentityGroupPermissionModel,
    IdentityOutboxModel,
    IdentityPermissionModel,
    IdentityRefreshTokenModel,
    IdentityServiceClientModel,
    IdentitySigningKeyModel,
    IdentityUserGroupModel,
    IdentityUserModel,
)
from identity_service.password import hash_secret, verify_secret

logger = logging.getLogger("identity_service.token_service")
_executor = ThreadPoolExecutor(max_workers=10)


class RobustEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime, date, and Decimal types."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


class InvalidUserRoleAssignmentsError(ValueError):
    """Raised when a human user carries SERVICE or unknown group assignments."""


async def _run_blocking(func, *args, **kwargs):
    """Run a blocking function in the background executor to keep event loop responsive."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, partial(func, *args, **kwargs))


def _mask_email(email: str) -> str:
    """Standardized PII masking for emails."""
    if "@" not in email:
        return "***"
    parts = email.split("@")
    name = parts[0]
    domain = parts[1]
    mask = name[0] + "***" + (name[-1] if len(name) > 1 else "")
    return f"{mask}@{domain}"


# ---------------------------------------------------------------------------
# Public utility helpers (promoted from private — used by admin router too)
# ---------------------------------------------------------------------------


def now_utc() -> datetime:
    return datetime.now(UTC)


def new_ulid() -> str:
    return str(ULID())


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def as_utc(value: datetime) -> datetime:
    """Normalize DB-loaded datetimes to timezone-aware UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


# Keep underscore aliases so any remaining internal callers don't break
_now_utc = now_utc
_new_ulid = new_ulid
_hash_token = hash_token
_as_utc = as_utc


def _signing_auth_settings(private_key: str, public_key: str) -> AuthSettings:
    return AuthSettings(
        algorithm=settings.auth_jwt_algorithm,
        issuer=settings.auth_issuer,
        audience=settings.auth_audience,
        private_key=private_key,
        public_key=public_key,
    )


def _bootstrap_service_clients() -> list[dict[str, str]]:
    """Return bootstrap service-client definitions from structured env or JSON fallback."""
    structured: list[dict[str, str]] = []
    for service_name in settings.bootstrap_service_names:
        client_secret = settings.service_client_secret(service_name)
        if not client_secret:
            continue
        structured.append(
            {
                "client_id": service_name,
                "service_name": service_name,
                "client_secret": client_secret,
            }
        )
    if structured:
        return structured

    try:
        client_defs = json.loads(settings.bootstrap_service_clients_json or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(client_defs, list):
        return []
    return [item for item in client_defs if isinstance(item, dict)]


async def _signing_private_key(signing_key: IdentitySigningKeyModel) -> str:
    """Decrypt the persisted signing key into PEM using background executor."""
    return await _run_blocking(
        decrypt_private_key, signing_key.private_key_ciphertext_b64, aad=signing_key.kid
    )


async def ensure_group(session: AsyncSession, group_name: str) -> IdentityGroupModel:
    """Create or fetch a named group."""
    result = await session.execute(
        select(IdentityGroupModel).where(IdentityGroupModel.group_name == group_name)
    )
    group = result.scalar_one_or_none()
    if group is not None:
        return group
    group = IdentityGroupModel(
        group_id=new_ulid(),
        group_name=group_name,
        description=f"Auto-managed group {group_name}",
    )
    session.add(group)
    await session.flush()
    return group


async def ensure_active_signing_key(session: AsyncSession) -> IdentitySigningKeyModel:
    """Return the active signing key, creating one if none exist.

    Uses SELECT FOR UPDATE to serialize concurrent key creation across pods,
    preventing duplicate key generation when the active key slot is empty.
    """
    result = await session.execute(
        select(IdentitySigningKeyModel)
        .where(IdentitySigningKeyModel.is_active.is_(True))
        .order_by(IdentitySigningKeyModel.created_at_utc.desc())
        .with_for_update()
    )
    key = result.scalars().first()
    if key is not None:
        return key

    private_key, public_key = generate_rsa_keypair()
    kid = new_ulid()
    private_key_ciphertext = await _run_blocking(encrypt_private_key, private_key, aad=kid)
    key = IdentitySigningKeyModel(
        kid=kid,
        algorithm=settings.auth_jwt_algorithm,
        public_key_pem=public_key,
        private_key_ciphertext_b64=private_key_ciphertext,
        private_key_kek_version=require_kek_version(),
        is_active=True,
        created_at_utc=now_utc(),
        retired_at_utc=None,
    )
    session.add(key)
    await session.flush()
    return key


async def seed_bootstrap_state(session: AsyncSession) -> None:
    """Seed bootstrap admin, groups, and service clients when missing."""
    for group_name in (
        str(PlatformRole.SUPER_ADMIN),
        str(PlatformRole.MANAGER),
        str(PlatformRole.OPERATOR),
    ):
        await ensure_group(session, group_name)

    user_count = await session.scalar(select(func.count()).select_from(IdentityUserModel))
    if not user_count:
        super_admin = IdentityUserModel(
            user_id=new_ulid(),
            username=settings.bootstrap_superadmin_username,
            email=settings.bootstrap_superadmin_email,
            password_hash=hash_secret(settings.bootstrap_superadmin_password),
            is_active=True,
            created_at_utc=now_utc(),
            updated_at_utc=now_utc(),
        )
        session.add(super_admin)
        await session.flush()
        super_admin_group = await ensure_group(session, str(PlatformRole.SUPER_ADMIN))
        session.add(
            IdentityUserGroupModel(
                user_id=super_admin.user_id,
                group_id=super_admin_group.group_id,
                assigned_at=now_utc(),
            )
        )
        await write_audit(
            session,
            "USER",
            super_admin.user_id,
            "CREATE",
            "SYSTEM",
            "SYSTEM",
            new_snapshot=serialize_user(super_admin, mask_pii=True),
        )

    for item in _bootstrap_service_clients():
        client_id = str(item.get("client_id", "")).strip()
        service_name = str(item.get("service_name", "")).strip()
        client_secret = str(item.get("client_secret", "")).strip()
        if not client_id or not service_name or not client_secret:
            continue
        existing = await session.get(IdentityServiceClientModel, client_id)
        if existing is None:
            session.add(
                IdentityServiceClientModel(
                    client_id=client_id,
                    service_name=service_name,
                    client_secret_hash=hash_secret(client_secret),
                    is_active=True,
                    created_at_utc=now_utc(),
                    rotated_at_utc=None,
                )
            )

    for p_key in ALL_CORE_PERMISSIONS:
        perm = await session.get(IdentityPermissionModel, p_key)
        if not perm:
            perm = IdentityPermissionModel(
                permission_key=p_key, description=f"Core permission: {p_key}"
            )
            session.add(perm)

    sa_group = await session.get(IdentityGroupModel, str(PlatformRole.SUPER_ADMIN))
    if sa_group:
        for p_key in ALL_CORE_PERMISSIONS:
            gp = await session.get(IdentityGroupPermissionModel, (sa_group.group_id, p_key))
            if not gp:
                gp = IdentityGroupPermissionModel(group_id=sa_group.group_id, permission_key=p_key)
                session.add(gp)

    logger.info("Bootstrap state synchronized (Users, Groups, Permissions).")


async def validate_bootstrap_state(session: AsyncSession) -> None:
    """Ensure the seeded superadmin and active signing key exist after bootstrap."""
    result = await session.execute(
        select(IdentityUserModel).where(
            IdentityUserModel.username == settings.bootstrap_superadmin_username
        )
    )
    if result.scalar_one_or_none() is None:
        raise RuntimeError("Bootstrap superadmin was not created.")
    signing_key = await ensure_active_signing_key(session)
    if not signing_key.private_key_ciphertext_b64:
        raise RuntimeError("Active signing key ciphertext is missing.")
    if not signing_key.private_key_kek_version:
        raise RuntimeError("Active signing key KEK version is missing.")


async def _user_groups(session: AsyncSession, user_id: str) -> list[str]:
    query = (
        select(IdentityGroupModel.group_name)
        .join(
            IdentityUserGroupModel,
            IdentityUserGroupModel.group_id == IdentityGroupModel.group_id,
        )
        .where(IdentityUserGroupModel.user_id == user_id)
    )
    result = await session.execute(query)
    return [str(name) for name in result.scalars().all()]


async def _permissions_for_groups(session: AsyncSession, group_names: list[str]) -> list[str]:
    if not group_names:
        return []
    query = (
        select(IdentityGroupPermissionModel.permission_key)
        .join(
            IdentityGroupModel,
            IdentityGroupModel.group_id == IdentityGroupPermissionModel.group_id,
        )
        .where(IdentityGroupModel.group_name.in_(group_names))
    )
    result = await session.execute(query)
    return sorted({str(item) for item in result.scalars().all()})


def _role_for_groups(group_names: list[str]) -> str:
    invalid_groups = sorted({item for item in group_names if item not in USER_ROLE_NAMES})
    if invalid_groups:
        raise InvalidUserRoleAssignmentsError("User role assignments invalid.")
    if not group_names:
        return str(PlatformRole.MANAGER)
    return max(group_names, key=lambda item: ROLE_PRIORITY.get(item, 0))


async def write_audit(
    session: AsyncSession,
    target_type: str,
    target_id: str,
    action_type: str,
    actor_id: str,
    actor_role: str,
    *,
    old_snapshot: dict | None = None,
    new_snapshot: dict | None = None,
    request_id: str | None = None,
) -> None:
    audit = IdentityAuditLogModel(
        audit_id=new_ulid(),
        target_type=target_type,
        target_id=target_id,
        action_type=action_type,
        actor_id=actor_id,
        actor_role=actor_role,
        old_snapshot_json=json.dumps(old_snapshot, cls=RobustEncoder) if old_snapshot else None,
        new_snapshot_json=json.dumps(new_snapshot, cls=RobustEncoder) if new_snapshot else None,
        request_id=request_id,
        created_at_utc=now_utc(),
    )
    session.add(audit)


# Keep underscore alias for any remaining callers
_write_audit = write_audit


async def _write_outbox(
    session: AsyncSession,
    event_name: str,
    payload: dict,
    *,
    aggregate_id: str,
    aggregate_type: str = "USER",
) -> None:
    outbox = IdentityOutboxModel(
        outbox_id=new_ulid(),
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        aggregate_version=1,
        event_name=event_name,
        event_version=1,
        payload_json=json.dumps(payload, cls=RobustEncoder),
        publish_status="PENDING",
        attempt_count=0,
        last_error_code=None,
        created_at_utc=now_utc(),
        next_attempt_at_utc=now_utc(),
        claim_expires_at_utc=None,
    )
    session.add(outbox)


def serialize_user(
    user: IdentityUserModel,
    *,
    mask_pii: bool = False,
    groups: list[str] | None = None,
    permissions: list[str] | None = None,
) -> dict[str, object]:
    email = user.email
    if mask_pii:
        email = _mask_email(email)

    data: dict[str, object] = {
        "user_id": user.user_id,
        "username": user.username,
        "email": email,
        "is_active": user.is_active,
        "created_at_utc": user.created_at_utc.isoformat() if user.created_at_utc else None,
        "updated_at_utc": user.updated_at_utc.isoformat() if user.updated_at_utc else None,
    }
    if groups is not None:
        data["groups"] = sorted(groups)
    if permissions is not None:
        data["permissions"] = sorted(permissions)
    return data


async def build_user_profile(session: AsyncSession, user: IdentityUserModel) -> dict[str, object]:
    """Return a normalized user profile used by /me and admin endpoints."""
    groups = await _user_groups(session, user.user_id)
    permissions = await _permissions_for_groups(session, groups)
    return {
        "user_id": user.user_id,
        "username": user.username,
        "email": user.email,
        "is_active": user.is_active,
        "groups": groups,
        "permissions": permissions,
        "role": _role_for_groups(groups),
        "created_at_utc": user.created_at_utc,
        "updated_at_utc": user.updated_at_utc,
    }


async def authenticate_user(
    session: AsyncSession, username: str, password: str
) -> IdentityUserModel | None:
    """Authenticate a user by username/password."""
    result = await session.execute(
        select(IdentityUserModel).where(IdentityUserModel.username == username)
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    if not verify_secret(password, user.password_hash):
        return None
    return user


async def _issue_user_access_token(
    signing_key: IdentitySigningKeyModel,
    private_key_pem: str,
    *,
    user_id: str,
    role: str,
    groups: list[str],
    permissions: list[str],
) -> str:
    ts = int(now_utc().timestamp())
    payload = {
        "sub": user_id,
        "role": role,
        "groups": groups,
        "permissions": permissions,
        "iss": settings.auth_issuer,
        "aud": settings.auth_audience,
        "iat": ts,
        "nbf": ts,
        "exp": ts + settings.access_token_ttl_seconds,
        "jti": uuid4().hex,
    }
    return await _run_blocking(
        issue_token,
        payload,
        _signing_auth_settings(private_key_pem, signing_key.public_key_pem),
        headers={"kid": signing_key.kid, "typ": "JWT"},
    )


async def _issue_service_access_token(
    signing_key: IdentitySigningKeyModel,
    private_key_pem: str,
    *,
    service_name: str,
    audience: str | None = None,
) -> str:
    ts = int(now_utc().timestamp())
    payload = {
        "sub": service_name,
        "role": str(PlatformRole.SERVICE),
        "service": service_name,
        "iss": settings.auth_issuer,
        "aud": audience or settings.auth_audience,
        "iat": ts,
        "nbf": ts,
        "exp": ts + settings.service_token_ttl_seconds,
        "jti": uuid4().hex,
        "typ": "S2S",
    }
    return await _run_blocking(
        issue_token,
        payload,
        _signing_auth_settings(private_key_pem, signing_key.public_key_pem),
        headers={"kid": signing_key.kid, "typ": "JWT"},
    )


async def issue_token_pair(
    session: AsyncSession,
    user: IdentityUserModel,
    *,
    family_id: str | None = None,
) -> dict[str, object]:
    """Issue and persist an access/refresh token pair for a user.

    If family_id is provided the new refresh token continues that family chain.
    If None a new family is started (first login or explicit new session).
    """
    profile = await build_user_profile(session, user)
    signing_key = await ensure_active_signing_key(session)
    private_key_pem = await _signing_private_key(signing_key)
    access_token = await _issue_user_access_token(
        signing_key,
        private_key_pem=private_key_pem,
        user_id=user.user_id,
        role=str(profile["role"]),
        groups=list(profile["groups"]),
        permissions=list(profile["permissions"]),
    )
    refresh_token = secrets.token_urlsafe(48)
    refresh_row = IdentityRefreshTokenModel(
        token_id=new_ulid(),
        user_id=user.user_id,
        token_hash=hash_token(refresh_token),
        family_id=family_id or new_ulid(),
        expires_at_utc=now_utc() + timedelta(seconds=settings.refresh_token_ttl_seconds),
        revoked_at_utc=None,
        created_at_utc=now_utc(),
    )
    session.add(refresh_row)
    await session.flush()
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.access_token_ttl_seconds,
    }


async def rotate_refresh_token(session: AsyncSession, raw_refresh_token: str) -> dict[str, object]:
    """Consume a refresh token and issue a replacement pair.

    Stolen token detection: if the presented token is already revoked,
    all tokens in its family are immediately revoked (RFC 6749 §10.4).
    """
    token_hash = hash_token(raw_refresh_token)
    result = await session.execute(
        select(IdentityRefreshTokenModel).where(IdentityRefreshTokenModel.token_hash == token_hash)
    )
    refresh_row = result.scalar_one_or_none()

    # Stolen token detection: revoked token reused → nuke the entire family.
    # The nuke must be committed in its own session because the caller will
    # rollback the outer session after we raise ValueError.
    if refresh_row is not None and refresh_row.revoked_at_utc is not None:
        if refresh_row.family_id:
            family_id = refresh_row.family_id
            user_id_for_log = refresh_row.user_id
            from identity_service.database import async_session_factory

            async with async_session_factory() as nuke_session:
                await nuke_session.execute(
                    update(IdentityRefreshTokenModel)
                    .where(
                        IdentityRefreshTokenModel.family_id == family_id,
                        IdentityRefreshTokenModel.revoked_at_utc.is_(None),
                    )
                    .values(revoked_at_utc=now_utc())
                )
                await nuke_session.commit()
            logger.warning(
                "Stolen token detected — revoked entire family %s for user %s",
                family_id,
                user_id_for_log,
            )
        raise ValueError(
            "Token reuse detected. All sessions for this family have been invalidated."
        )

    if refresh_row is None or as_utc(refresh_row.expires_at_utc) <= now_utc():
        raise ValueError("Refresh token is invalid or expired.")

    user = await session.get(IdentityUserModel, refresh_row.user_id)
    if user is None or not user.is_active:
        raise ValueError("Refresh token owner is inactive.")

    refresh_row.revoked_at_utc = now_utc()
    token_pair = await issue_token_pair(session, user, family_id=refresh_row.family_id)
    await session.flush()
    return token_pair


async def revoke_refresh_token(session: AsyncSession, raw_refresh_token: str) -> None:
    """Revoke a refresh token if it exists."""
    token_hash = hash_token(raw_refresh_token)
    result = await session.execute(
        select(IdentityRefreshTokenModel).where(IdentityRefreshTokenModel.token_hash == token_hash)
    )
    refresh_row = result.scalar_one_or_none()
    if refresh_row is not None and refresh_row.revoked_at_utc is None:
        refresh_row.revoked_at_utc = now_utc()


async def issue_service_token(
    session: AsyncSession,
    client_id: str,
    client_secret: str,
    audience: str | None,
) -> dict[str, object]:
    """Issue a service token after validating client credentials.

    Cross-audience tokens (audience != platform audience) are only permitted
    when auth_strict_audience_check=True and the audience is a registered service.
    With the default (strict=False) only same-platform-audience tokens are issued.
    """
    client = await session.get(IdentityServiceClientModel, client_id)
    if (
        client is None
        or not client.is_active
        or not verify_secret(client_secret, client.client_secret_hash)
    ):
        raise ValueError("Service client credentials are invalid.")

    if audience and audience != settings.auth_audience:
        if not settings.auth_strict_audience_check:
            raise ValueError(
                "Cross-service audience tokens are disabled. "
                "Set IDENTITY_AUTH_STRICT_AUDIENCE_CHECK=true to enable."
            )
        if audience not in settings.bootstrap_service_names:
            raise ValueError("Requested audience is not a registered service.")

    signing_key = await ensure_active_signing_key(session)
    access_token = await _issue_service_access_token(
        signing_key,
        private_key_pem=await _signing_private_key(signing_key),
        service_name=client.service_name,
        audience=audience or settings.auth_audience,
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.service_token_ttl_seconds,
    }


async def decode_access_token(session: AsyncSession, token: str):
    """Verify an access token against the persisted signing keys.

    Rejects tokens signed with retired keys and tokens whose jti is blocklisted
    (e.g. after explicit logout).
    """
    header = jwt.get_unverified_header(token)
    kid = str(header.get("kid", "")).strip()
    if not kid:
        raise ValueError("Token is missing kid.")
    signing_key = await session.get(IdentitySigningKeyModel, kid)
    if signing_key is None:
        raise ValueError("Signing key not found.")
    if signing_key.retired_at_utc is not None:
        raise ValueError("Token was signed with a retired key.")
    auth_settings = AuthSettings(
        algorithm=signing_key.algorithm,
        public_key=signing_key.public_key_pem,
        issuer=settings.auth_issuer,
        audience=settings.auth_audience,
    )
    claims = verify_token(token, auth_settings)

    # JTI blocklist check (post-logout / post-deactivation revocation)
    from identity_service.blocklist import is_token_blocked

    jti = _extract_jti(claims)
    if jti and await is_token_blocked(jti):
        raise ValueError("Token has been revoked.")

    return claims


def _extract_jti(claims: Any) -> str | None:
    """Extract jti from a claims object robustly."""
    if hasattr(claims, "jti") and claims.jti:
        return str(claims.jti)
    if isinstance(claims, dict):
        return str(claims.get("jti")) if claims.get("jti") else None
    return None


async def assign_groups(
    session: AsyncSession, user: IdentityUserModel, group_names: list[str]
) -> None:
    """Replace a user's group memberships and emit outbox event."""
    await session.execute(
        delete(IdentityUserGroupModel).where(IdentityUserGroupModel.user_id == user.user_id)
    )
    for group_name in group_names:
        group = await ensure_group(session, group_name)
        session.add(
            IdentityUserGroupModel(
                user_id=user.user_id,
                group_id=group.group_id,
                assigned_at=now_utc(),
            )
        )
    await _write_outbox(
        session,
        "identity.user.groups_assigned.v1",
        {
            "user_id": user.user_id,
            "groups": sorted(group_names),
            "occurred_at_utc": now_utc().isoformat(),
        },
        aggregate_id=user.user_id,
    )


async def jwks_document(session: AsyncSession) -> dict[str, object]:
    """Return the published JWKS document (active, non-retired keys only)."""
    result = await session.execute(
        select(IdentitySigningKeyModel).where(IdentitySigningKeyModel.retired_at_utc.is_(None))
    )
    keys = [
        public_key_to_jwk(row.public_key_pem, row.kid, row.algorithm)
        for row in result.scalars().all()
    ]
    return {"keys": keys}
