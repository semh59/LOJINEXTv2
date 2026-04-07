from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict
from uuid import uuid4

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from telegram_service.observability import (
    BOT_UPDATES_TOTAL,
    get_correlation_id,
    get_standard_labels,
    reset_correlation_id,
    set_correlation_id,
)


class AuditMiddleware(BaseMiddleware):
    """Middleware to ensure every aiogram event has a correlation ID."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # If we are in a FastAPI request (webhook), the ContextVar might already be set.
        # If not (polling), we generate one.
        cid = get_correlation_id()
        if not cid:
            cid = f"bot-{uuid4().hex[:8]}"

        # Record metrics
        update_type = type(event).__name__
        labels = get_standard_labels()
        BOT_UPDATES_TOTAL.labels(update_type=update_type, **labels).inc()

        token = set_correlation_id(cid)
        try:
            return await handler(event, data)
        finally:
            reset_correlation_id(token)
