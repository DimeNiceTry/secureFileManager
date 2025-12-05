from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from loguru import logger

from ..models import Directory, User
from ..database import get_database_manager

class DirectoryService:

    def __init__(self):

        self.db_manager = get_database_manager()

    async def get_or_create_root_directory(self, user: User, db: AsyncSession) -> Directory:

        try:

            result = await db.execute(
                select(Directory)
                .where(Directory.owner_id == user.id)
                .where(Directory.path == "/")
            )
            root_dir = result.scalar_one_or_none()

            if not root_dir:

                root_dir = Directory(
                    name="/",
                    path="/",
                    parent_id=None,
                    owner_id=user.id
                )
                db.add(root_dir)
                await db.commit()
                await db.refresh(root_dir)

            return root_dir
        except Exception as e:
            logger.error(f"Error getting/creating root directory: {e}")
            await db.rollback()
            raise

    async def create_directory(self, name: str, parent_path: str, user: User, db: AsyncSession) -> Directory:

        try:

            await self.get_or_create_root_directory(user, db)

            if parent_path.endswith("/") and len(parent_path) > 1:
                parent_path = parent_path.rstrip("/")

            new_path = f"{parent_path}/{name}" if parent_path != "/" else f"/{name}"

            result = await db.execute(
                select(Directory)
                .where(Directory.owner_id == user.id)
                .where(Directory.path == new_path)
                .where(Directory.is_active == True)
            )
            if result.scalar_one_or_none():
                raise ValueError(f"Directory '{name}' already exists in '{parent_path}'")

            parent_dir = None
            if parent_path != "/":
                result = await db.execute(
                    select(Directory)
                    .where(Directory.owner_id == user.id)
                    .where(Directory.path == parent_path)
                    .where(Directory.is_active == True)
                )
                parent_dir = result.scalar_one_or_none()
                if not parent_dir:
                    raise ValueError(f"Parent directory '{parent_path}' does not exist")
            else:

                result = await db.execute(
                    select(Directory)
                    .where(Directory.owner_id == user.id)
                    .where(Directory.path == "/")
                )
                parent_dir = result.scalar_one_or_none()

            new_dir = Directory(
                name=name,
                path=new_path,
                parent_id=parent_dir.id if parent_dir else None,
                owner_id=user.id
            )

            db.add(new_dir)
            await db.commit()
            await db.refresh(new_dir)

            logger.info(f"Directory created: {new_path} by {user.username}")
            return new_dir

        except Exception as e:
            logger.error(f"Error creating directory: {e}")
            await db.rollback()
            raise

    async def get_directory_by_path(self, path: str, user: User, db: AsyncSession) -> Optional[Directory]:

        try:
            if path.endswith("/") and len(path) > 1:
                path = path.rstrip("/")

            result = await db.execute(
                select(Directory)
                .where(Directory.owner_id == user.id)
                .where(Directory.path == path)
                .where(Directory.is_active == True)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"Error getting directory by path: {e}")
            return None

    async def list_directories(self, parent_path: str, user: User, db: AsyncSession) -> List[Directory]:

        try:

            await self.get_or_create_root_directory(user, db)

            if parent_path.endswith("/") and len(parent_path) > 1:
                parent_path = parent_path.rstrip("/")

            parent_dir = await self.get_directory_by_path(parent_path, user, db)
            if not parent_dir:
                return []

            result = await db.execute(
                select(Directory)
                .where(Directory.owner_id == user.id)
                .where(Directory.parent_id == parent_dir.id)
                .where(Directory.is_active == True)
                .order_by(Directory.name)
            )
            return list(result.scalars().all())

        except Exception as e:
            logger.error(f"Error listing directories: {e}")
            return []

    async def delete_directory(self, path: str, user: User, db: AsyncSession, recursive: bool = False) -> bool:

        try:
            if path == "/":
                raise ValueError("Cannot delete root directory")

            directory = await self.get_directory_by_path(path, user, db)
            if not directory:
                return False

            result = await db.execute(
                select(Directory)
                .where(Directory.parent_id == directory.id)
                .where(Directory.is_active == True)
            )
            children = list(result.scalars().all())

            if children and not recursive:
                raise ValueError("Directory is not empty. Use -r flag to delete recursively.")

            directory.is_active = False

            if recursive:
                await self._delete_recursive(directory.id, db)

            await db.commit()

            logger.info(f"Directory deleted: {path} by {user.username}")
            return True

        except Exception as e:
            logger.error(f"Error deleting directory: {e}")
            await db.rollback()
            raise

    async def _delete_recursive(self, directory_id: int, db: AsyncSession):

        result = await db.execute(
            select(Directory)
            .where(Directory.parent_id == directory_id)
            .where(Directory.is_active == True)
        )
        children = list(result.scalars().all())

        for child in children:
            child.is_active = False
            await self._delete_recursive(child.id, db)

    async def resolve_path(self, path: str, current_path: str) -> str:

        if path.startswith("/"):
            return path

        if path == "..":
            if current_path == "/":
                return "/"
            parts = current_path.split("/")
            if len(parts) > 2:
                return "/".join(parts[:-1])
            else:
                return "/"

        if path == ".":
            return current_path

        if current_path == "/":
            return f"/{path}"
        else:
            return f"{current_path}/{path}"