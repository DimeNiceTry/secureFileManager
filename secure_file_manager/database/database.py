import asyncio
from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy import text
from loguru import logger

from ..config import get_settings
from ..models import Base

class DatabaseManager:

    def __init__(self) -> None:
        self.settings = get_settings()
        self.engine: Optional[AsyncEngine] = None
        self._initialized = False

    async def initialize(self) -> None:

        if self._initialized:
            return

        try:
            self.engine = create_async_engine(
                self.settings.database_url,
                echo=self.settings.db_echo,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                pool_recycle=3600,
            )

            await self._wait_for_database()

            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            self._initialized = True
            logger.info("Database initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    async def _wait_for_database(self, max_retries: int = 30, retry_delay: float = 2.0) -> None:

        for attempt in range(max_retries):
            try:
                if self.engine:
                    async with self.engine.begin() as conn:
                        await conn.execute(text("SELECT 1"))
                    logger.info("Database connection established")
                    return
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed to connect to database after {max_retries} attempts")
                    raise
                logger.warning(f"Database not ready (attempt {attempt + 1}/{max_retries}): {e}")
                await asyncio.sleep(retry_delay)

    async def close(self) -> None:

        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self._initialized = False
            logger.info("Database connections closed")

    @property
    def is_initialized(self) -> bool:

        return self._initialized

_database_manager: Optional[DatabaseManager] = None

def get_database_manager() -> DatabaseManager:

    global _database_manager
    if _database_manager is None:
        _database_manager = DatabaseManager()
    return _database_manager