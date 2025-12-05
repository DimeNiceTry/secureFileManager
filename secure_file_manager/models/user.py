from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import List, TYPE_CHECKING

from .base import Base

if TYPE_CHECKING:
    from .file import File
    from .directory import Directory
    from .operation import Operation
    from .operation import Operation

class User(Base):

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False
    )
    is_admin: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False
    )

    files: Mapped[List["File"]] = relationship(
        "File",
        back_populates="owner",
        cascade="all, delete-orphan"
    )
    directories: Mapped[List["Directory"]] = relationship(
        "Directory",
        back_populates="owner",
        cascade="all, delete-orphan"
    )
    operations: Mapped[List["Operation"]] = relationship(
        "Operation",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', is_active={self.is_active})>"