from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .database import get_database_manager

AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = None

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:

    global AsyncSessionLocal

    db_manager = get_database_manager()

    if not db_manager.is_initialized:
        await db_manager.initialize()

    if AsyncSessionLocal is None and db_manager.engine:
        AsyncSessionLocal = async_sessionmaker(
            db_manager.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=True,
            autocommit=False
        )

    if AsyncSessionLocal is None:
        raise RuntimeError("Database session factory not initialized")

    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()