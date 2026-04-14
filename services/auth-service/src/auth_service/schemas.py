"""Pydantic request/response models for auth-service."""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=512)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=512)

class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=256)

class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=256)

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

class MeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: str
    email: EmailStr
    is_active: bool
    role: str
    created_at_utc: datetime
    updated_at_utc: datetime

class JWKSResponse(BaseModel):
    keys: list[dict[str, object]]
