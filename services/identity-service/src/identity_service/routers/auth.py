"""Authentication and JWKS endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from identity_service.auth import current_user
from identity_service.database import get_session
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
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    token_pair = await issue_token_pair(session, user)
    await session.commit()
    return TokenPairResponse(**token_pair)


@router.post("/auth/v1/logout", status_code=200)
async def logout(
    body: LogoutRequest, session: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    """Revoke a refresh token."""
    await revoke_refresh_token(session, body.refresh_token)
    await session.commit()
    return {"status": "LOGGED_OUT"}


@router.post("/auth/v1/refresh", response_model=TokenPairResponse)
async def refresh(
    body: RefreshRequest, session: AsyncSession = Depends(get_session)
) -> TokenPairResponse:
    """Rotate a refresh token into a fresh token pair."""
    try:
        token_pair = await rotate_refresh_token(session, body.refresh_token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
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
        status_code = 400 if "audience" in str(exc).lower() else 401
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    await session.commit()
    return ServiceTokenResponse(**result)


@router.get(
    "/.well-known/jwks.json", response_model=JWKSResponse, include_in_schema=False
)
async def jwks(session: AsyncSession = Depends(get_session)) -> JWKSResponse:
    """Expose the published JWKS document."""
    return JWKSResponse(**(await jwks_document(session)))
