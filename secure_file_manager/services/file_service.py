import os
import shutil
import asyncio
import mimetypes
from pathlib import Path
from typing import Optional, BinaryIO, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from loguru import logger

from ..models import File, User, OperationType, Directory
from ..config import get_settings
from .crypto_service import CryptoService
from .operation_service import OperationService
from .json_xml_service import JsonXmlService

class FileService:

    def __init__(self, crypto_service: CryptoService, operation_service: OperationService):
        self.crypto_service = crypto_service
        self.operation_service = operation_service
        self.json_xml_service = JsonXmlService()
        self.settings = get_settings()
        self.root_path = Path(self.settings.root_storage_path)
        self.shared_path = Path("shared")
        self._ensure_root_directory()
        self._ensure_shared_directory()
        self._lock = asyncio.Lock()

    def _ensure_root_directory(self) -> None:
        try:
            self.root_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Storage directory ready: {self.root_path}")
        except Exception as e:
            logger.error(f"Failed to create storage directory: {e}")
            raise

    def _ensure_shared_directory(self) -> None:
        try:
            self.shared_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Shared directory ready: {self.shared_path}")
        except Exception as e:
            logger.error(f"Failed to create shared directory: {e}")
            raise

    def _validate_filename(self, filename: str) -> str:
        if not filename or len(filename) > 255:
            raise ValueError("Filename must be 1-255 characters long")

        dangerous_chars = '<>:"|?*\\/\x00'
        for char in dangerous_chars:
            filename = filename.replace(char, '_')

        filename = filename.replace('..', '_')

        if not filename.strip('._'):
            raise ValueError("Invalid filename after sanitization")

        return filename.strip()

    def _get_user_storage_path(self, user: User) -> Path:
        user_dir = self.root_path / f"user_{user.id}"
        user_dir.mkdir(exist_ok=True)
        return user_dir

    def _get_safe_file_path(self, user: User, filename: str) -> Path:

        sanitized_filename = self._validate_filename(filename)
        user_storage = self._get_user_storage_path(user)
        file_path = user_storage / sanitized_filename

        file_path = file_path.resolve()

        try:
            file_path.relative_to(user_storage.resolve())
        except ValueError:
            raise ValueError("Path traversal attempt detected!")

        return file_path

    async def create_file(
        self,
        session: AsyncSession,
        user: User,
        filename: str,
        content: bytes,
        encrypt: bool = False,
        directory_id: Optional[int] = None,
        ip_address: Optional[str] = None
    ) -> File:
        async with self._lock:
            try:
                if len(content) > self.settings.max_file_size:
                    raise ValueError(f"File size exceeds maximum allowed ({self.settings.max_file_size} bytes)")

                if filename.lower().endswith(('.json', '.xml')):
                    content_str = content.decode('utf-8', errors='replace')
                    if not self.json_xml_service.validate_file_format(filename, content_str):
                        raise ValueError(f"Invalid {filename.split('.')[-1].upper()} format")

                file_path = self._get_safe_file_path(user, filename)

                query = select(File).where(
                    and_(
                        File.original_name == filename,
                        File.owner_id == user.id
                    )
                )
                if directory_id is not None:
                    query = query.where(File.directory_id == directory_id)
                else:
                    query = query.where(File.directory_id.is_(None))

                result = await session.execute(query)
                if result.scalar_one_or_none() is not None:
                    raise ValueError("File with this name already exists")

                final_content = content
                encryption_key = None

                if encrypt:
                    encryption_key = self.crypto_service.generate_file_encryption_key()
                    final_content = self.crypto_service.encrypt_data(content, encryption_key)

                file_path.write_bytes(final_content)

                checksum = self.crypto_service.calculate_file_checksum(str(file_path))

                mime_type, _ = mimetypes.guess_type(filename)

                file_obj = File(
                    filename=file_path.name,
                    original_name=filename,
                    size=len(content),
                    mime_type=mime_type,
                    checksum=checksum,
                    storage_path=str(file_path),
                    is_encrypted=encrypt,
                    owner_id=user.id,
                    directory_id=directory_id
                )

                session.add(file_obj)
                await session.commit()
                await session.refresh(file_obj)

                await self.operation_service.log_operation(
                    session=session,
                    user=user,
                    operation_type=OperationType.CREATE,
                    details=f"Created file: {filename} (encrypted: {encrypt})",
                    file=file_obj,
                    ip_address=ip_address
                )

                logger.info(f"File created successfully: {filename} by {user.username}")
                return file_obj

            except Exception as e:

                await self.operation_service.log_operation(
                    session=session,
                    user=user,
                    operation_type=OperationType.CREATE,
                    details=f"Failed to create file: {filename}",
                    ip_address=ip_address,
                    success=False,
                    error_message=str(e)
                )
                logger.error(f"File creation failed for {filename}: {e}")
                raise

    async def read_file(
        self,
        session: AsyncSession,
        user: User,
        file_id: int,
        ip_address: Optional[str] = None
    ) -> Tuple[File, bytes]:

        try:

            result = await session.execute(
                select(File).where(
                    and_(
                        File.id == file_id,
                        File.owner_id == user.id
                    )
                )
            )
            file_obj = result.scalar_one_or_none()

            if file_obj is None:
                raise ValueError("File not found or access denied")

            file_path = Path(file_obj.storage_path)
            if not file_path.exists():
                raise ValueError("File not found on disk")

            content = file_path.read_bytes()

            if file_obj.is_encrypted:

                raise ValueError("Encrypted file reading not implemented in this demo")

            await self.operation_service.log_operation(
                session=session,
                user=user,
                operation_type=OperationType.READ,
                details=f"Read file: {file_obj.original_name}",
                file=file_obj,
                ip_address=ip_address
            )

            logger.info(f"File read successfully: {file_obj.original_name} by {user.username}")
            return file_obj, content

        except Exception as e:

            await self.operation_service.log_operation(
                session=session,
                user=user,
                operation_type=OperationType.READ,
                details=f"Failed to read file ID: {file_id}",
                ip_address=ip_address,
                success=False,
                error_message=str(e)
            )
            logger.error(f"File read failed for ID {file_id}: {e}")
            raise

    async def update_file(
        self,
        session: AsyncSession,
        user: User,
        file_id: int,
        new_content: bytes,
        ip_address: Optional[str] = None
    ) -> File:

        async with self._lock:
            try:

                result = await session.execute(
                    select(File).where(
                        and_(
                            File.id == file_id,
                            File.owner_id == user.id
                        )
                    )
                )
                file_obj = result.scalar_one_or_none()

                if file_obj is None:
                    raise ValueError("File not found or access denied")

                if len(new_content) > self.settings.max_file_size:
                    raise ValueError(f"File size exceeds maximum allowed ({self.settings.max_file_size} bytes)")

                file_path = Path(file_obj.storage_path)

                final_content = new_content
                if file_obj.is_encrypted:

                    raise ValueError("Encrypted file updating not implemented in this demo")

                file_path.write_bytes(final_content)

                file_obj.size = len(new_content)
                file_obj.checksum = self.crypto_service.calculate_file_checksum(str(file_path))

                await session.commit()

                await self.operation_service.log_operation(
                    session=session,
                    user=user,
                    operation_type=OperationType.UPDATE,
                    details=f"Updated file: {file_obj.original_name}",
                    file=file_obj,
                    ip_address=ip_address
                )

                logger.info(f"File updated successfully: {file_obj.original_name} by {user.username}")
                return file_obj

            except Exception as e:

                await self.operation_service.log_operation(
                    session=session,
                    user=user,
                    operation_type=OperationType.UPDATE,
                    details=f"Failed to update file ID: {file_id}",
                    ip_address=ip_address,
                    success=False,
                    error_message=str(e)
                )
                logger.error(f"File update failed for ID {file_id}: {e}")
                raise

    async def delete_file(
        self,
        session: AsyncSession,
        user: User,
        file_id: int,
        ip_address: Optional[str] = None
    ) -> bool:

        async with self._lock:
            try:

                result = await session.execute(
                    select(File).where(
                        and_(
                            File.id == file_id,
                            File.owner_id == user.id
                        )
                    )
                )
                file_obj = result.scalar_one_or_none()

                if file_obj is None:
                    raise ValueError("File not found or access denied")

                file_path = Path(file_obj.storage_path)
                filename = file_obj.original_name

                if file_path.exists():
                    file_path.unlink()

                await session.delete(file_obj)
                await session.commit()

                await self.operation_service.log_operation(
                    session=session,
                    user=user,
                    operation_type=OperationType.DELETE,
                    details=f"Deleted file: {filename}",
                    ip_address=ip_address
                )

                logger.info(f"File deleted successfully: {filename} by {user.username}")
                return True

            except Exception as e:

                await self.operation_service.log_operation(
                    session=session,
                    user=user,
                    operation_type=OperationType.DELETE,
                    details=f"Failed to delete file ID: {file_id}",
                    ip_address=ip_address,
                    success=False,
                    error_message=str(e)
                )
                logger.error(f"File deletion failed for ID {file_id}: {e}")
                raise

    async def list_user_files(
        self,
        session: AsyncSession,
        user: User,
        directory_id: Optional[int] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[File]:

        query = select(File).where(File.owner_id == user.id)

        if directory_id is not None:
            query = query.where(File.directory_id == directory_id)
        else:

            query = query.where(File.directory_id.is_(None))

        result = await session.execute(
            query.order_by(File.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_file_by_name(
        self,
        session: AsyncSession,
        user: User,
        filename: str
    ) -> Optional[File]:

        result = await session.execute(
            select(File).where(
                and_(
                    File.original_name == filename,
                    File.owner_id == user.id
                )
            )
        )
        return result.scalar_one_or_none()

    def get_storage_info(self, user: User) -> dict:

        user_storage = self._get_user_storage_path(user)

        total_size = 0
        file_count = 0

        for file_path in user_storage.rglob('*'):
            if file_path.is_file():
                total_size += file_path.stat().st_size
                file_count += 1

        return {
            'storage_path': str(user_storage),
            'total_size': total_size,
            'file_count': file_count,
            'max_file_size': self.settings.max_file_size,
            'available_space': self.settings.max_file_size * 1000 - total_size
        }

    def list_shared_files(self) -> List[dict]:
        shared_files = []
        
        if not self.shared_path.exists():
            return shared_files
            
        for file_path in self.shared_path.iterdir():
            if file_path.is_file():
                stat = file_path.stat()
                shared_files.append({
                    'name': file_path.name,
                    'size': stat.st_size,
                    'modified': stat.st_mtime
                })
        
        return shared_files

    async def copy_from_shared(
        self,
        session: AsyncSession,
        user: User,
        shared_filename: str,
        new_filename: Optional[str] = None,
        directory_id: Optional[int] = None,
        ip_address: Optional[str] = None
    ) -> File:
        shared_file_path = self.shared_path / shared_filename
        
        if not shared_file_path.exists():
            raise ValueError(f"Shared file not found: {shared_filename}")
        
        if not shared_file_path.is_file():
            raise ValueError(f"Path is not a file: {shared_filename}")
        
        content = shared_file_path.read_bytes()
        filename = new_filename or shared_filename
        
        return await self.create_file(
            session=session,
            user=user,
            filename=filename,
            content=content,
            encrypt=False,
            directory_id=directory_id,
            ip_address=ip_address
        )