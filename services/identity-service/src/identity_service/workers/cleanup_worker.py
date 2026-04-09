"""Nightly cleanup worker: purge expired refresh tokens and old audit logs."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from identity_service.database import async_session_factory
from identity_service.models import IdentityAuditLogModel, IdentityRefreshTokenModel

logger = logging.getLogger("identity_service.cleanup_worker")

# Audit logs older than this many days are deleted.
AUDIT_LOG_RETENTION_DAYS = 90
# Refresh tokens are purged this many days after expiry (grace period).
REFRESH_TOKEN_PURGE_GRACE_DAYS = 1
# How often the cleanup loop runs (seconds).
CLEANUP_INTERVAL_SECONDS = 86_400  # daily


async def _purge_expired_refresh_tokens() -> int:
    cutoff = datetime.now(UTC) - timedelta(days=REFRESH_TOKEN_PURGE_GRACE_DAYS)
    async with async_session_factory() as session:
        result = await session.execute(
            delete(IdentityRefreshTokenModel)
            .where(IdentityRefreshTokenModel.expires_at_utc < cutoff)
            .returning(IdentityRefreshTokenModel.token_id)
        )
        deleted = len(result.fetchall())
        await session.commit()
    return deleted


async def _purge_old_audit_logs() -> int:
    cutoff = datetime.now(UTC) - timedelta(days=AUDIT_LOG_RETENTION_DAYS)
    async with async_session_factory() as session:
        result = await session.execute(
            delete(IdentityAuditLogModel)
            .where(IdentityAuditLogModel.created_at_utc < cutoff)
            .returning(IdentityAuditLogModel.audit_id)
        )
        deleted = len(result.fetchall())
        await session.commit()
    return deleted


async def run_cleanup(*, shutdown_event: asyncio.Event | None = None) -> None:
    """Run nightly cleanup tasks until shutdown_event is set."""
    logger.info("Cleanup worker started (interval=%ds)", CLEANUP_INTERVAL_SECONDS)

    while True:
        if shutdown_event and shutdown_event.is_set():
            logger.info("Cleanup worker: shutdown signal received, exiting cleanly.")
            return

        try:
            tokens_deleted = await _purge_expired_refresh_tokens()
            logger.info("Cleanup: purged %d expired refresh tokens", tokens_deleted)
        except Exception:  # noqa: BLE001
            logger.exception("Cleanup: failed to purge expired refresh tokens")

        try:
            logs_deleted = await _purge_old_audit_logs()
            logger.info("Cleanup: purged %d old audit log entries", logs_deleted)
        except Exception:  # noqa: BLE001
            logger.exception("Cleanup: failed to purge old audit logs")

        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
