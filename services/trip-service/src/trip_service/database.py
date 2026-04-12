"""Async SQLAlchemy engine and session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from trip_service.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_recycle=settings.db_pool_recycle_seconds,
    connect_args={
        "command_timeout": 15,  # 15s absolute statement limit
        "server_settings": {
            "statement_timeout": "15000",  # 15s
            "lock_timeout": "5000",  # 5s to fail early on deadlocks
            "idle_in_transaction_session_timeout": "30000",  # 30s to kill stale sessions
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
