import os
import zipfile
import py7zr
from pathlib import Path
from typing import List, Optional, Set
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from ..models import User, File, OperationType
from ..config import get_settings
from .file_service import FileService
from .operation_service import OperationService

class ArchiveService:

    def __init__(self, file_service: FileService, operation_service: OperationService):
        self.file_service = file_service
        self.operation_service = operation_service
        self.settings = get_settings()

    async def create_zip_archive(
        self,
        session: AsyncSession,
        user: User,
        file_ids: List[int],
        archive_name: str,
        ip_address: Optional[str] = None
    ) -> File:
        try:

            if not archive_name.endswith('.zip'):
                archive_name += '.zip'

            archive_path = self.file_service._get_safe_file_path(user, archive_name)

            files_to_archive = []
            total_size = 0

            for file_id in file_ids:
                file_obj, content = await self.file_service.read_file(session, user, file_id, ip_address)
                files_to_archive.append((file_obj, content))
                total_size += len(content)

                if total_size > self.settings.max_file_size * 10:
                    raise ValueError("Total archive size would exceed limits")

            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
                for file_obj, content in files_to_archive:
                    zipf.writestr(file_obj.original_name, content)

            archive_content = archive_path.read_bytes()

            archive_file = await self.file_service.create_file(
                session=session,
                user=user,
                filename=archive_name,
                content=archive_content,
                encrypt=False,
                ip_address=ip_address
            )

            await self.operation_service.log_operation(
                session=session,
                user=user,
                operation_type=OperationType.ARCHIVE_CREATE,
                details=f"Created archive {archive_name} with {len(file_ids)} files",
                file=archive_file,
                ip_address=ip_address
            )

            archive_path.unlink()

            logger.info(f"ZIP archive created: {archive_name} by {user.username}")
            return archive_file

        except Exception as e:

            await self.operation_service.log_operation(
                session=session,
                user=user,
                operation_type=OperationType.ARCHIVE_CREATE,
                details=f"Failed to create archive: {archive_name}",
                ip_address=ip_address,
                success=False,
                error_message=str(e)
            )
            logger.error(f"Archive creation failed: {e}")
            raise

    async def extract_zip_archive(
        self,
        session: AsyncSession,
        user: User,
        archive_file_id: int,
        ip_address: Optional[str] = None
    ) -> List[File]:

        extracted_files = []
        temp_dir = None

        try:

            archive_obj, archive_content = await self.file_service.read_file(
                session, user, archive_file_id, ip_address
            )

            user_storage = self.file_service._get_user_storage_path(user)
            temp_dir = user_storage / f"temp_extract_{archive_obj.id}"
            temp_dir.mkdir(exist_ok=True)

            temp_archive_path = temp_dir / "archive.zip"
            temp_archive_path.write_bytes(archive_content)

            extracted_files = await self._safe_zip_extraction(
                temp_archive_path, temp_dir, session, user, ip_address
            )

            await self.operation_service.log_operation(
                session=session,
                user=user,
                operation_type=OperationType.ARCHIVE_EXTRACT,
                details=f"Extracted {len(extracted_files)} files from {archive_obj.original_name}",
                file=archive_obj,
                ip_address=ip_address
            )

            logger.info(
                f"ZIP archive extracted: {archive_obj.original_name} "
                f"({len(extracted_files)} files) by {user.username}"
            )

        except Exception as e:

            await self.operation_service.log_operation(
                session=session,
                user=user,
                operation_type=OperationType.ARCHIVE_EXTRACT,
                details=f"Failed to extract archive ID: {archive_file_id}",
                ip_address=ip_address,
                success=False,
                error_message=str(e)
            )
            logger.error(f"Archive extraction failed: {e}")
            raise

        finally:

            if temp_dir and temp_dir.exists():
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)

        return extracted_files

    async def _safe_zip_extraction(
        self,
        archive_path: Path,
        extract_dir: Path,
        session: AsyncSession,
        user: User,
        ip_address: Optional[str]
    ) -> List[File]:

        extracted_files = []

        try:
            with zipfile.ZipFile(archive_path, 'r') as zipf:

                self._validate_zip_archive(zipf)

                for file_info in zipf.infolist():

                    if file_info.is_dir():
                        continue

                    self._validate_zip_entry(file_info, extract_dir)

                    file_content = zipf.read(file_info)

                    extracted_file = await self.file_service.create_file(
                        session=session,
                        user=user,
                        filename=f"extracted_{file_info.filename}",
                        content=file_content,
                        encrypt=False,
                        ip_address=ip_address
                    )

                    extracted_files.append(extracted_file)

        except zipfile.BadZipFile:
            raise ValueError("Invalid or corrupted ZIP archive")
        except Exception as e:
            logger.error(f"ZIP extraction error: {e}")
            raise ValueError(f"Archive extraction failed: {e}")

        return extracted_files

    def _validate_zip_archive(self, zipf: zipfile.ZipFile) -> None:

        total_uncompressed_size = 0
        file_count = 0
        compression_ratios = []

        for file_info in zipf.infolist():
            if file_info.is_dir():
                continue

            file_count += 1
            total_uncompressed_size += file_info.file_size

            if file_info.file_size > self.settings.max_file_size:
                raise ValueError(f"File {file_info.filename} exceeds size limit")

            if file_info.compress_size > 0:
                ratio = file_info.file_size / file_info.compress_size
                compression_ratios.append(ratio)

                if ratio > 100:
                    raise ValueError(f"Suspicious compression ratio detected for {file_info.filename}")

            if '..' in file_info.filename or file_info.filename.startswith('/'):
                raise ValueError(f"Dangerous path detected: {file_info.filename}")

        if file_count > self.settings.max_archive_files:
            raise ValueError(f"Archive contains too many files (limit: {self.settings.max_archive_files})")

        if total_uncompressed_size > self.settings.max_zip_size:
            raise ValueError(f"Archive uncompressed size exceeds limit ({self.settings.max_zip_size} bytes)")

        if compression_ratios and sum(compression_ratios) / len(compression_ratios) > 50:
            raise ValueError("Average compression ratio is suspiciously high (potential ZIP bomb)")

        logger.debug(f"ZIP validation passed: {file_count} files, {total_uncompressed_size} bytes")

    def _validate_zip_entry(self, file_info: zipfile.ZipInfo, extract_dir: Path) -> None:

        sanitized_name = self.file_service._validate_filename(file_info.filename)

        final_path = (extract_dir / sanitized_name).resolve()

        try:
            final_path.relative_to(extract_dir.resolve())
        except ValueError:
            raise ValueError(f"Path traversal attempt: {file_info.filename}")

        reserved_names = {
            'CON', 'PRN', 'AUX', 'NUL',
            'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
            'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
        }

        if sanitized_name.upper().split('.')[0] in reserved_names:
            raise ValueError(f"Reserved filename: {file_info.filename}")

    async def list_archive_contents(
        self,
        session: AsyncSession,
        user: User,
        archive_file_id: int
    ) -> List[dict]:

        try:

            archive_obj, archive_content = await self.file_service.read_file(
                session, user, archive_file_id
            )

            user_storage = self.file_service._get_user_storage_path(user)
            temp_archive = user_storage / f"temp_list_{archive_obj.id}.zip"
            temp_archive.write_bytes(archive_content)

            contents = []

            try:
                with zipfile.ZipFile(temp_archive, 'r') as zipf:
                    for file_info in zipf.infolist():
                        if not file_info.is_dir():
                            contents.append({
                                'filename': file_info.filename,
                                'size': file_info.file_size,
                                'compressed_size': file_info.compress_size,
                                'compression_ratio': (
                                    file_info.file_size / file_info.compress_size
                                    if file_info.compress_size > 0 else 0
                                ),
                                'date_time': file_info.date_time
                            })
            finally:
                temp_archive.unlink(missing_ok=True)

            return contents

        except Exception as e:
            logger.error(f"Failed to list archive contents: {e}")
            raise ValueError(f"Cannot read archive contents: {e}")

    def get_supported_formats(self) -> List[str]:

        return ['.zip']