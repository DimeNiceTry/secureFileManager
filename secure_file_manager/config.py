from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, validator
from pydantic_settings import BaseSettings

class Settings(BaseSettings):

    database_url: str = Field(
        default="postgresql+asyncpg://user:password@db:5432/secure_db",
        description="Database connection URL"
    )

    secret_key: str = Field(
        default="your-secret-key-here-change-in-production",
        description="Secret key for JWT tokens"
    )
    algorithm: str = Field(default="HS256", description="JWT algorithm")
    access_token_expire_minutes: int = Field(
        default=30,
        description="Access token expiration time in minutes"
    )

    root_storage_path: str = Field(
        default="/app/safe_storage",
        description="Root path for secure file storage"
    )
    max_file_size: int = Field(
        default=104857600,
        description="Maximum file size in bytes"
    )
    max_zip_size: int = Field(
        default=10485760,
        description="Maximum ZIP archive size for extraction"
    )
    max_archive_files: int = Field(
        default=1000,
        description="Maximum number of files in archive"
    )

    debug: bool = Field(default=False, description="Debug mode")
    log_level: str = Field(default="WARNING", description="Logging level")
    db_echo: bool = Field(default=False, description="Echo SQL queries")

    @validator("root_storage_path")
    def validate_storage_path(cls, v: str) -> str:

        path = Path(v)
        if not path.is_absolute():
            raise ValueError("Storage path must be absolute")
        return str(path)

    @validator("secret_key")
    def validate_secret_key(cls, v: str) -> str:

        if len(v) < 32:
            raise ValueError("Secret key must be at least 32 characters long")
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

@lru_cache()
def get_settings() -> Settings:

    return Settings()