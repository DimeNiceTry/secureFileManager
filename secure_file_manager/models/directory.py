from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base

class Directory(Base):

    __tablename__ = "directories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    path = Column(String(1000), nullable=False, index=True)
    parent_id = Column(Integer, ForeignKey("directories.id"), nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now(), nullable=False)

    owner = relationship("User", back_populates="directories")
    parent = relationship("Directory", remote_side=[id], back_populates="children")
    children = relationship("Directory", back_populates="parent")
    files = relationship("File", back_populates="directory")