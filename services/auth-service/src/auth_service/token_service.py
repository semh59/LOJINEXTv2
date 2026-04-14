"""Core token services."""

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
from typing import Any
from uuid import uuid4

import jwt
from platform_auth import AuthSettings, PlatformRole, verify_token
from platform_auth.jwt_codec import issue_token
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from auth_service.config import settings
from auth_service.crypto import (
    decrypt_private_key,
    encrypt_private_key,
    require_kek_version,
)
from auth_service.jwks import generate_rsa_keypair, public_key_to_jwk
from auth_service.models import (
    AuthAuditLogModel,
    AuthCredentials,
    AuthOutboxModel,
    AuthRefreshTokenModel,
    AuthSigningKeyModel,
    AuthServiceClientModel,
)
from auth_service.password import hash_secret, verify_secret

logger = logging.getLogger("auth_service.token_service")
_executor = ThreadPoolExecutor(max_workers=10)


class RobustEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)

async def _run_blocking(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, partial(func, *args, **kwargs))

def now_utc() -> datetime:
    return datetime.now(UTC)

def new_ulid() -> str:
    return str(ULID())

def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)

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

async def _signing_private_key(signing_key: AuthSigningKeyModel) -> str:
    return await _run_blocking(
        decrypt_private_key, signing_key.private_key_ciphertext_b64, aad=signing_key.kid
    )

async def ensure_active_signing_key(session: AsyncSession) -> AuthSigningKeyModel:
    result = await session.execute(
        select(AuthSigningKeyModel)
        .where(AuthSigningKeyModel.is_active.is_(True))
        .order_by(AuthSigningKeyModel.created_at_utc.desc())
        .with_for_update()
    )
    key = result.scalars().first()
    if key is not None:
        return key

    private_key, public_key = generate_rsa_keypair()
    kid = new_ulid()
    private_key_ciphertext = await _run_blocking(encrypt_private_key, private_key, aad=kid)
    key = AuthSigningKeyModel(
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

# Note: We temporarily issue tokens without hitting identity-service.
async def _issue_user_access_token(
    signing_key: AuthSigningKeyModel,
    private_key_pem: str,
    *,
    user_id: str,
) -> str:
    ts = int(now_utc().timestamp())
    payload = {
        "sub": user_id,
        "role": str(PlatformRole.OPERATOR),
        "groups": [],
        "permissions": [],
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

async def register_user(
    session: AsyncSession, email: str, password: str, request_id: str | None = None
) -> AuthCredentials:
    user_id = new_ulid()
    hashed_password = hash_secret(password)
    # Create credentials
    cred = AuthCredentials(
        id=user_id,
        email=email,
        hashed_password=hashed_password,
        is_active=True,
        created_at_utc=now_utc(),
        updated_at_utc=now_utc(),
    )
    session.add(cred)

    # Create audit log entry
    audit_id = new_ulid()
    audit_log = AuthAuditLogModel(
        audit_id=audit_id,
        target_type="USER",
        target_id=user_id,
        action_type="USER_REGISTERED",
        actor_id=user_id,
        actor_role="USER",
        old_snapshot_json=None,
        new_snapshot_json=json.dumps({"email": email}, cls=RobustEncoder),
        request_id=request_id,
        created_at_utc=now_utc(),
    )
    session.add(audit_log)

    # Create outbox event
    outbox = AuthOutboxModel(
        outbox_id=new_ulid(),
        aggregate_type="USER",
        aggregate_id=user_id,
        aggregate_version=1,
        event_name="user.registered",
        event_version=1,
        payload_json=json.dumps(
            {"user_id": user_id, "email": email, "occurred_at_utc": now_utc().isoformat()},
            cls=RobustEncoder,
        ),
        publish_status="PENDING",
        attempt_count=0,
        created_at_utc=now_utc(),
        next_attempt_at_utc=now_utc(),
        correlation_id=str(uuid4()),
    )
    session.add(outbox)
    await session.flush()
    return cred

async def authenticate_user(
    session: AsyncSession, email: str, password: str
) -> AuthCredentials | None:
    result = await session.execute(
        select(AuthCredentials).where(AuthCredentials.email == email)
    )
    cred = result.scalar_one_or_none()
    if cred is None or not cred.is_active:
        return None
    if not verify_secret(password, cred.hashed_password):
        return None
    return cred

async def issue_token_pair(
    session: AsyncSession,
    cred: AuthCredentials,
    *,
    family_id: str | None = None,
) -> dict[str, object]:
    signing_key = await ensure_active_signing_key(session)
    private_key_pem = await _signing_private_key(signing_key)
    access_token = await _issue_user_access_token(
        signing_key,
        private_key_pem=private_key_pem,
        user_id=str(cred.id),
    )
    refresh_token = secrets.token_urlsafe(48)
    refresh_row = AuthRefreshTokenModel(
        token_id=new_ulid(),
        user_id=cred.id,
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
    token_hash = hash_token(raw_refresh_token)
    result = await session.execute(
        select(AuthRefreshTokenModel).where(AuthRefreshTokenModel.token_hash == token_hash)
    )
    refresh_row = result.scalar_one_or_none()

    if refresh_row is not None and refresh_row.revoked_at_utc is not None:
        if refresh_row.family_id:
            family_id = refresh_row.family_id
            user_id_for_log = refresh_row.user_id
            from auth_service.database import async_session_factory
            async with async_session_factory() as nuke_session:
                await nuke_session.execute(
                    update(AuthRefreshTokenModel)
                    .where(
                        AuthRefreshTokenModel.family_id == family_id,
                        AuthRefreshTokenModel.revoked_at_utc.is_(None),
                    )
                    .values(revoked_at_utc=now_utc())
                )
                await nuke_session.commit()
            logger.warning(
                "Stolen token detected revoked entire family %s for user %s",
                family_id,
                user_id_for_log,
            )
        raise ValueError("Token reuse detected. All sessions for this family have been invalidated.")

    if refresh_row is None or as_utc(refresh_row.expires_at_utc) <= now_utc():
        raise ValueError("Refresh token is invalid or expired.")

    cred = await session.get(AuthCredentials, refresh_row.user_id)
    if cred is None or not cred.is_active:
        raise ValueError("Refresh token owner is inactive.")

    refresh_row.revoked_at_utc = now_utc()
    token_pair = await issue_token_pair(session, cred, family_id=refresh_row.family_id)
    await session.flush()
    return token_pair

async def revoke_refresh_token(session: AsyncSession, raw_refresh_token: str) -> None:
    token_hash = hash_token(raw_refresh_token)
    result = await session.execute(
        select(AuthRefreshTokenModel).where(AuthRefreshTokenModel.token_hash == token_hash)
    )
    refresh_row = result.scalar_one_or_none()
    if refresh_row is not None and refresh_row.revoked_at_utc is None:
        refresh_row.revoked_at_utc = now_utc()

def _extract_jti(claims: Any) -> str | None:
    if hasattr(claims, "jti") and claims.jti:
        return str(claims.jti)
    if isinstance(claims, dict):
        return str(claims.get("jti")) if claims.get("jti") else None
    return None

async def decode_access_token(session: AsyncSession, token: str):
    header = jwt.get_unverified_header(token)
    kid = str(header.get("kid", "")).strip()
    if not kid:
        raise ValueError("Token is missing kid.")
    signing_key = await session.get(AuthSigningKeyModel, kid)
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
    return claims

async def jwks_document(session: AsyncSession) -> dict[str, object]:
    result = await session.execute(
        select(AuthSigningKeyModel).where(AuthSigningKeyModel.retired_at_utc.is_(None))
    )
    keys = [
        public_key_to_jwk(row.public_key_pem, row.kid, row.algorithm)
        for row in result.scalars().all()
    ]
    return {"keys": keys}

async def _issue_service_access_token(
    signing_key: AuthSigningKeyModel,
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

async def issue_service_token(
    session: AsyncSession,
    client_id: str,
    client_secret: str,
    audience: str | None,
) -> dict[str, object]:
    client = await session.get(AuthServiceClientModel, client_id)
    if (
        client is None
        or not client.is_active
        or not verify_secret(client_secret, client.client_secret_hash)
    ):
        raise ValueError("Service client credentials are invalid.")

    if audience and audience != settings.auth_audience:
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

class InvalidUserRoleAssignmentsError(Exception):
    """Raised when there is an issue with user role assignments."""
    pass

async def build_user_profile(session: AsyncSession, user: AuthCredentials) -> dict[str, object]:
    """Build a basic user profile for the /me endpoint."""
    return {
        "user_id": str(user.id),
        "email": user.email,
        "is_active": user.is_active,
        "role": str(PlatformRole.OPERATOR),  # Default role for now as auth-service only handles authentication
        "created_at_utc": user.created_at_utc,
        "updated_at_utc": user.updated_at_utc,
    }
