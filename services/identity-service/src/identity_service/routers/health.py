"""Health and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from identity_service.crypto import require_kek_bytes, require_kek_version
from identity_service.database import get_session

router = APIRouter(prefix="/v1", tags=["health"])
