"""Authentication and JWKS endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from identity_service.auth import current_user
from identity_service.blocklist import block_token
from identity_service.database import get_session
from identity_service.errors import (
    identity_conflict,
    identity_unauthorized,
    identity_validation_error,
)
from identity_service.schemas import (
    JWKSResponse,
    LoginRequest,
    LogoutRequest,
    MeResponse,
    RefreshRequest,
    ServiceTokenRequest,
    ServiceTokenResponse,
    TokenPairResponse,
)
from identity_service.token_service import (
    InvalidUserRoleAssignmentsError,
    authenticate_user,
    issue_service_token,
    issue_token_pair,
    jwks_document,
    revoke_refresh_token,
    rotate_refresh_token,
)

router = APIRouter(tags=["identity-auth"])


@router.post("/auth/v1/login", response_model=TokenPairResponse)
async def login(
    body: LoginRequest, session: AsyncSession = Depends(get_session)
) -> TokenPairResponse:
    """Authenticate a user and issue access/refresh tokens."""
    user = await authenticate_user(session, body.username, body.password)
    if user is None:
        raise identity_unauthorized("Invalid username or password.")
    try:
        token_pair = await issue_token_pair(session, user)
    except InvalidUserRoleAssignmentsError as exc:
        await session.rollback()
        raise identity_conflict(str(exc)) from exc
    await session.commit()
    return TokenPairResponse(**token_pair)


@router.post("/auth/v1/logout", status_code=200)
async def logout(
    body: LogoutRequest,
    session: AsyncSession = Depends(get_session),
    authorization: str | None = Header(None, alias="Authorization"),
) -> dict[str, str]:
    """Revoke a refresh token and blocklist the current access token."""
    await revoke_refresh_token(session, body.refresh_token)

    # Best-effort: blocklist the access token so it cannot be reused after logout
    if authorization and authorization.lower().startswith("bearer "):
        raw_token = authorization[7:].strip()
        try:
            payload = jwt.decode(raw_token, options={"verify_signature": False})
            jti = payload.get("jti")
            exp = payload.get("exp", 0)
            ttl = max(0, exp - int(datetime.now(UTC).timestamp()))
            if jti and ttl > 0:
                await block_token(jti, ttl_seconds=ttl)
        except Exception:
            pass  # best-effort; refresh token revocation is the primary action

    await session.commit()
    return {"status": "LOGGED_OUT"}


@router.post("/auth/v1/refresh", response_model=TokenPairResponse)
async def refresh(
    body: RefreshRequest, session: AsyncSession = Depends(get_session)
) -> TokenPairResponse:
    """Rotate a refresh token into a fresh token pair."""
    try:
        token_pair = await rotate_refresh_token(session, body.refresh_token)
    except InvalidUserRoleAssignmentsError as exc:
        await session.rollback()
        raise identity_conflict(str(exc)) from exc
    except ValueError as exc:
        await session.rollback()
        raise identity_unauthorized(str(exc)) from exc
    await session.commit()
    return TokenPairResponse(**token_pair)


@router.get("/auth/v1/me", response_model=MeResponse)
async def me(user: dict[str, object] = Depends(current_user)) -> MeResponse:
    """Return the current caller profile."""
    return MeResponse(**user)


@router.post("/auth/v1/token/service", response_model=ServiceTokenResponse)
async def service_token(
    body: ServiceTokenRequest,
    session: AsyncSession = Depends(get_session),
) -> ServiceTokenResponse:
    """Issue a short-lived service token for internal service-to-service auth."""
    try:
        result = await issue_service_token(
            session, body.client_id, body.client_secret, body.audience
        )
    except ValueError as exc:
        if "audience" in str(exc).lower():
            raise identity_validation_error(str(exc)) from exc
        raise identity_unauthorized(str(exc)) from exc
    await session.commit()
    return ServiceTokenResponse(**result)


@router.get(
    "/.well-known/jwks.json", response_model=JWKSResponse, include_in_schema=False
)
async def jwks(session: AsyncSession = Depends(get_session)) -> JWKSResponse:
    """Expose the published JWKS document."""
    return JWKSResponse(**(await jwks_document(session)))
