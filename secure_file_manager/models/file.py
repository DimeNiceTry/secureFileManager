from sqlalchemy import String, BigInteger, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List, TYPE_CHECKING

from .base import Base

if TYPE_CHECKING:
    from .user import User
    from .operation import Operation
    from .directory import Directory

class File(Base):

    __tablename__ = "files"

    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True
    )
    original_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    size: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False
    )
    mime_type: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True
    )
    checksum: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True
    )
    storage_path: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    is_encrypted: Mapped[bool] = mapped_column(
        default=False,
        nullable=False
    )

    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    directory_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("directories.id", ondelete="SET NULL"),
        nullable=True
    )

    owner: Mapped["User"] = relationship(
        "User",
        back_populates="files"
    )
    directory: Mapped[Optional["Directory"]] = relationship(
        "Directory",
        back_populates="files"
    )
    operations: Mapped[List["Operation"]] = relationship(
        "Operation",
        back_populates="file",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<File(id={self.id}, filename='{self.filename}', size={self.size})>"