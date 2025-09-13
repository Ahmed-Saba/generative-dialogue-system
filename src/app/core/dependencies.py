from app.database.session import get_async_session
from sqlalchemy.ext.asyncio import AsyncSession

async def get_db_session() -> AsyncSession:
    # Returns DB session dependency
    return get_async_session()

