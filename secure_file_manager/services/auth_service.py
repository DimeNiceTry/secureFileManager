from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

from ..models import User, Operation, OperationType
from .crypto_service import CryptoService
from .operation_service import OperationService

class AuthService:

    def __init__(self, crypto_service: CryptoService, operation_service: OperationService):
        self.crypto_service = crypto_service
        self.operation_service = operation_service

    async def register_user(
        self,
        session: AsyncSession,
        username: str,
        password: str,
        is_admin: bool = False
    ) -> User:

        if not self._validate_username(username):
            raise ValueError("Username must be 3-50 characters long and contain only alphanumeric characters and underscores")

        if not self._validate_password(password):
            raise ValueError("Password must be at least 8 characters long and contain uppercase, lowercase, and numeric characters")

        result = await session.execute(
            select(User).where(User.username == username)
        )
        if result.scalar_one_or_none() is not None:
            raise ValueError("Username already exists")

        password_hash = self.crypto_service.hash_password(password)

        user = User(
            username=username,
            password_hash=password_hash,
            is_admin=is_admin
        )

        session.add(user)
        await session.commit()
        await session.refresh(user)

        logger.info(f"New user registered: {username}")
        return user

    async def authenticate_user(
        self,
        session: AsyncSession,
        username: str,
        password: str,
        ip_address: Optional[str] = None
    ) -> Optional[User]:

        try:

            result = await session.execute(
                select(User).where(
                    User.username == username,
                    User.is_active == True
                )
            )
            user = result.scalar_one_or_none()

            if user is None:
                await self._log_failed_login(session, username, "User not found", ip_address)
                return None

            if not self.crypto_service.verify_password(password, user.password_hash):
                await self._log_failed_login(session, username, "Invalid password", ip_address)
                return None

            if self.crypto_service.needs_rehash(user.password_hash):
                user.password_hash = self.crypto_service.hash_password(password)
                await session.commit()
                logger.info(f"Updated password hash for user: {username}")

            await self.operation_service.log_operation(
                session=session,
                user=user,
                operation_type=OperationType.LOGIN,
                details="Successful login",
                ip_address=ip_address,
                success=True
            )

            logger.info(f"User authenticated successfully: {username}")
            return user

        except Exception as e:
            logger.error(f"Authentication error for {username}: {e}")
            await self._log_failed_login(session, username, f"Authentication error: {e}", ip_address)
            return None

    async def _log_failed_login(
        self,
        session: AsyncSession,
        username: str,
        reason: str,
        ip_address: Optional[str] = None
    ) -> None:

        try:

            result = await session.execute(
                select(User.id).where(User.username == username)
            )
            user_id = result.scalar_one_or_none()

            if user_id:

                temp_user = User(id=user_id, username=username, password_hash="", is_active=True)

                await self.operation_service.log_operation(
                    session=session,
                    user=temp_user,
                    operation_type=OperationType.LOGIN,
                    details=f"Failed login: {reason}",
                    ip_address=ip_address,
                    success=False,
                    error_message=reason
                )

            logger.warning(f"Failed login attempt for {username}: {reason}")

        except Exception as e:
            logger.error(f"Failed to log unsuccessful login for {username}: {e}")

    def _validate_username(self, username: str) -> bool:

        if not username or len(username) < 3 or len(username) > 50:
            return False

        return username.replace('_', '').isalnum()

    def _validate_password(self, password: str) -> bool:

        if not password or len(password) < 8:
            return False

        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)

        return has_upper and has_lower and has_digit

    async def get_user_by_id(self, session: AsyncSession, user_id: int) -> Optional[User]:

        result = await session.execute(
            select(User).where(
                User.id == user_id,
                User.is_active == True
            )
        )
        return result.scalar_one_or_none()

    async def deactivate_user(self, session: AsyncSession, user_id: int) -> bool:

        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            return False

        user.is_active = False
        await session.commit()

        logger.info(f"User deactivated: {user.username}")
        return True