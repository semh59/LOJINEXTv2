"""Async SQLAlchemy engine and session factory.

Provides the shared database engine used by the entire service.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from location_service.config import settings

engine = create_async_engine(settings.database_url, echo=False)

async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for providing database sessions to endpoints."""
    async with async_session_factory() as session:
        yield session
