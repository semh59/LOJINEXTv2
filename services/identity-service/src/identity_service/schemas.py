"""Pydantic request/response models for identity-service."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=512)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class ServiceTokenRequest(BaseModel):
    client_id: str = Field(min_length=1, max_length=64)
    client_secret: str = Field(min_length=1, max_length=512)
    audience: str | None = Field(default=None, max_length=128)


class ServiceTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    username: str
    email: EmailStr
    is_active: bool
    groups: list[str]
    permissions: list[str]
    created_at_utc: datetime
    updated_at_utc: datetime


class MeResponse(UserResponse):
    role: str


class AdminCreateUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    email: EmailStr
    password: str = Field(min_length=8, max_length=512)
    groups: list[str] = Field(default_factory=list)
    is_active: bool = True


class AdminUpdateUserRequest(BaseModel):
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=512)
    groups: list[str] | None = None
    is_active: bool | None = None


class JWKSResponse(BaseModel):
    keys: list[dict[str, object]]
