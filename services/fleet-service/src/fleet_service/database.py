"""Async SQLAlchemy engine and session management."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from fleet_service.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    connect_args={
        "command_timeout": 20,
        "server_settings": {
            "statement_timeout": "20000",
            "lock_timeout": "5000",
            "idle_in_transaction_session_timeout": "30000",
        },
    },
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session. Used as a FastAPI dependency."""
    async with async_session_factory() as session:
        yield session


# FastAPI dependency type alias
AsyncSessionDep = Annotated[AsyncSession, Depends(get_session)]
