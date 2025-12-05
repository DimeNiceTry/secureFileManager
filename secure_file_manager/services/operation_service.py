from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from loguru import logger

from ..models import Operation, OperationType, User, File

class OperationService:

    async def log_operation(
        self,
        session: AsyncSession,
        user: User,
        operation_type: OperationType,
        details: Optional[str] = None,
        file: Optional[File] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> Operation:

        operation = Operation(
            operation_type=operation_type,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            error_message=error_message,
            user_id=user.id,
            file_id=file.id if file else None
        )

        session.add(operation)

        try:
            await session.commit()
            await session.refresh(operation)

            logger.debug(
                f"Operation logged: {operation_type.value} by {user.username} "
                f"(success: {success})"
            )

        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to log operation: {e}")
            raise

        return operation

    async def get_user_operations(
        self,
        session: AsyncSession,
        user_id: int,
        limit: int = 100,
        offset: int = 0,
        operation_type: Optional[OperationType] = None
    ) -> list[Operation]:

        query = select(Operation).where(Operation.user_id == user_id)

        if operation_type:
            query = query.where(Operation.operation_type == operation_type)

        query = query.order_by(desc(Operation.created_at)).limit(limit).offset(offset)

        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_file_operations(
        self,
        session: AsyncSession,
        file_id: int,
        limit: int = 50
    ) -> list[Operation]:

        query = (
            select(Operation)
            .where(Operation.file_id == file_id)
            .order_by(desc(Operation.created_at))
            .limit(limit)
        )

        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_recent_operations(
        self,
        session: AsyncSession,
        limit: int = 100
    ) -> list[Operation]:

        query = (
            select(Operation)
            .order_by(desc(Operation.created_at))
            .limit(limit)
        )

        result = await session.execute(query)
        return list(result.scalars().all())

    async def get_failed_operations(
        self,
        session: AsyncSession,
        limit: int = 100
    ) -> list[Operation]:

        query = (
            select(Operation)
            .where(Operation.success == False)
            .order_by(desc(Operation.created_at))
            .limit(limit)
        )

        result = await session.execute(query)
        return list(result.scalars().all())

    async def count_user_operations(
        self,
        session: AsyncSession,
        user_id: int,
        operation_type: Optional[OperationType] = None
    ) -> int:

        from sqlalchemy import func

        query = select(func.count(Operation.id)).where(Operation.user_id == user_id)

        if operation_type:
            query = query.where(Operation.operation_type == operation_type)

        result = await session.execute(query)
        return result.scalar() or 0