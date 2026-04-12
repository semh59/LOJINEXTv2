"""Async SQLAlchemy engine and session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from identity_service.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=20,  # Standardizing for high-concurrency login pressure
    max_overflow=10,
    pool_recycle=3600,
    connect_args={
        "command_timeout": 5,  # Identity should be ultra-fast (5s limit)
        "server_settings": {
            "statement_timeout": "5000",
            "lock_timeout": "2000",
            "idle_in_transaction_session_timeout": "10000",
        },
    },
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session."""
    async with async_session_factory() as session:
        yield session
