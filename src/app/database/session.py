from typing import AsyncGenerator
from app.config import settings
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)

# Create the AsyncEngine.
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.SQLALCHEMY_ECHO,   # Set to False in production
    future=True,
    pool_pre_ping=True,              # Enables connection health checks
)

# `async_sessionmaker` returns an async session factory.
AsyncSessionMaker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Dependency to get DB session
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency. Yields a session and ensures it's closed after the request.

    Usage:
        async def endpoint(db: AsyncSession = Depends(get_async_session)):
            await db.execute(...)
    """
    async with AsyncSessionMaker() as session:
        yield session

