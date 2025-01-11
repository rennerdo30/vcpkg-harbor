from enum import Enum
from typing import Optional
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, validator


class StorageType(str, Enum):
    FILE = "file"
    MINIO = "minio"


class ServerSettings(BaseSettings):
    """Server configuration settings."""
    host: str = Field(default="0.0.0.0", env="VCPKG_HOST")
    port: int = Field(default=15151, env="VCPKG_PORT")
    workers: int = Field(default=4, env="VCPKG_WORKERS")
    read_only: bool = Field(default=False, env="VCPKG_READ_ONLY")
    write_only: bool = Field(default=False, env="VCPKG_WRITE_ONLY")

    model_config = SettingsConfigDict(env_prefix="VCPKG_", extra="allow")


class LogSettings(BaseSettings):
    """Logging configuration settings."""
    level: str = Field(default="INFO", env="VCPKG_LOG_LEVEL")
    json_format: bool = Field(default=True, env="VCPKG_LOG_JSON")
    file: Optional[str] = Field(default="logs/vcpkg-harbor.log", env="VCPKG_LOG_FILE")
    retention_days: int = Field(default=30, env="VCPKG_LOG_RETENTION_DAYS")

    @validator("level")
    def validate_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level. Must be one of: {valid_levels}")
        return v.upper()

    model_config = SettingsConfigDict(env_prefix="VCPKG_", extra="allow")


class FileStorageSettings(BaseSettings):
    """File storage configuration settings."""
    path: str = Field(default="./cache", env="VCPKG_STORAGE_PATH")
    work_dir: Optional[str] = Field(default=None, env="VCPKG_STORAGE_WORK_DIR")

    @validator("path")
    def validate_path(cls, v: str) -> str:
        """Validate and normalize storage path."""
        try:
            # Convert to absolute path and normalize
            path = Path(v).resolve()
            # Create directory if it doesn't exist
            path.mkdir(parents=True, exist_ok=True)
            return str(path)
        except Exception as e:
            raise ValueError(f"Invalid storage path: {e}")

    @validator("work_dir", pre=True, always=True)
    def set_work_dir(cls, v: Optional[str], values: dict) -> str:
        """Set work directory to {path}/.work if not specified."""
        if not v:
            base_path = Path(values.get("path", "./cache"))
            return str(base_path / ".work")
        return v

    model_config = SettingsConfigDict(env_prefix="VCPKG_", extra="allow")


class MinioStorageSettings(BaseSettings):
    """MinIO storage configuration settings."""
    endpoint: str = Field(default="localhost:9000", env="VCPKG_MINIO_ENDPOINT")
    access_key: str = Field(default="minioadmin", env="VCPKG_MINIO_ACCESS_KEY")
    secret_key: str = Field(default="minioadmin", env="VCPKG_MINIO_SECRET_KEY")
    bucket: str = Field(default="vcpkg-harbor", env="VCPKG_MINIO_BUCKET")
    region: Optional[str] = Field(default=None, env="VCPKG_MINIO_REGION")
    secure: bool = Field(default=True, env="VCPKG_MINIO_SECURE")

    model_config = SettingsConfigDict(env_prefix="VCPKG_", extra="allow")


class Settings(BaseSettings):
    """Global application settings."""
    storage_type: StorageType = Field(
        default=StorageType.FILE,
        env="VCPKG_STORAGE_TYPE"
    )

    server: ServerSettings = ServerSettings()
    logging: LogSettings = LogSettings()
    file_storage: FileStorageSettings = FileStorageSettings()
    minio_storage: Optional[MinioStorageSettings] = None

    @validator("storage_type", pre=True)
    def validate_storage_type(cls, v: str) -> StorageType:
        """Validate storage type."""
        try:
            return StorageType(v.lower())
        except ValueError:
            raise ValueError(f"Invalid storage type. Must be one of: {list(StorageType)}")

    @validator("minio_storage", always=True)
    def validate_minio_settings(cls, v: Optional[MinioStorageSettings], values: dict) -> Optional[MinioStorageSettings]:
        """Initialize MinIO settings only if needed."""
        if values.get("storage_type") == StorageType.MINIO:
            return MinioStorageSettings()
        return None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
        case_sensitive=False
    )


# Create global settings instance
settings = Settings()