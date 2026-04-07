"""Aiogram Bot and Dispatcher initialization."""

from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from telegram_service.config import settings


def build_bot() -> Bot:
    """Return a configured Bot instance."""
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def build_dispatcher() -> Dispatcher:
    """Return a configured Dispatcher with FSM storage."""
    storage: MemoryStorage
    if settings.redis_url:
        from aiogram.fsm.storage.redis import RedisStorage  # type: ignore[import-untyped]

        storage = RedisStorage.from_url(settings.redis_url)
    else:
        storage = MemoryStorage()

    dp = Dispatcher(storage=storage)

    # Register handler routers
    from telegram_service.handlers.common import router as common_router
    from telegram_service.handlers.slip import router as slip_router
    from telegram_service.handlers.statement import router as statement_router

    dp.include_router(slip_router)
    dp.include_router(statement_router)
    dp.include_router(common_router)  # common must be last (catches unmatched messages)

    return dp
