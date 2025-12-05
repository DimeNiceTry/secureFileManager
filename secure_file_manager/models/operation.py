import enum
from sqlalchemy import String, ForeignKey, Text, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, TYPE_CHECKING

from .base import Base

if TYPE_CHECKING:
    from .user import User
    from .file import File

class OperationType(enum.Enum):

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    MOVE = "move"
    COPY = "copy"
    ARCHIVE_CREATE = "archive_create"
    ARCHIVE_EXTRACT = "archive_extract"
    LOGIN = "login"
    LOGOUT = "logout"
    PERMISSION_DENIED = "permission_denied"

    def __str__(self) -> str:
        return self.value

class Operation(Base):

    __tablename__ = "operations"

    operation_type: Mapped[OperationType] = mapped_column(
        Enum(OperationType),
        nullable=False,
        index=True
    )
    details: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    success: Mapped[bool] = mapped_column(
        default=True,
        nullable=False
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    file_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=True
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="operations"
    )
    file: Mapped[Optional["File"]] = relationship(
        "File",
        back_populates="operations"
    )

    def __repr__(self) -> str:
        return f"<Operation(id={self.id}, type={self.operation_type}, user_id={self.user_id})>"