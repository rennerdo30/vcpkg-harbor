"""Configuration management for vcpkg-harbor using Pydantic Settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerSettings(BaseSettings):
    """Server configuration settings."""

    model_config = SettingsConfigDict(
        env_prefix="VCPKG_SERVER_",
        env_file=".env",
        extra="ignore",
    )

    host: str = Field(default="0.0.0.0", description="Host to bind the server to")
    port: int = Field(default=15151, description="Port to bind the server to")
    workers: int = Field(default=4, description="Number of worker processes")
    reload: bool = Field(default=False, description="Enable auto-reload for development")
    read_only: bool = Field(default=False, description="Run server in read-only mode")
    write_only: bool = Field(default=False, description="Run server in write-only mode")


class StorageSettings(BaseSettings):
    """Storage configuration settings."""

    model_config = SettingsConfigDict(
        env_prefix="VCPKG_STORAGE_",
        env_file=".env",
        extra="ignore",
    )

    type: Literal["minio", "filesystem", "s3", "azure", "gcs"] = Field(
        default="filesystem",
        description="Storage backend type",
    )
    path: str = Field(
        default="./cache",
        description="Local path for filesystem storage",
    )


class MinioSettings(BaseSettings):
    """MinIO storage backend configuration."""

    model_config = SettingsConfigDict(
        env_prefix="VCPKG_MINIO_",
        env_file=".env",
        extra="ignore",
    )

    endpoint: str = Field(default="localhost:9000", description="MinIO endpoint")
    access_key: str = Field(default="minioadmin", description="MinIO access key")
    secret_key: str = Field(default="minioadmin", description="MinIO secret key")
    bucket: str = Field(default="vcpkg-harbor", description="MinIO bucket name")
    secure: bool = Field(default=False, description="Use HTTPS for MinIO connection")
    region: str | None = Field(default=None, description="MinIO region")


class S3Settings(BaseSettings):
    """AWS S3 storage backend configuration."""

    model_config = SettingsConfigDict(
        env_prefix="VCPKG_S3_",
        env_file=".env",
        extra="ignore",
    )

    bucket: str = Field(default="vcpkg-harbor", description="S3 bucket name")
    region: str = Field(default="us-east-1", description="AWS region")
    access_key_id: str | None = Field(default=None, description="AWS access key ID")
    secret_access_key: str | None = Field(default=None, description="AWS secret access key")
    endpoint_url: str | None = Field(default=None, description="Custom S3 endpoint URL")


class AzureSettings(BaseSettings):
    """Azure Blob storage backend configuration."""

    model_config = SettingsConfigDict(
        env_prefix="VCPKG_AZURE_",
        env_file=".env",
        extra="ignore",
    )

    connection_string: str | None = Field(default=None, description="Azure connection string")
    account_name: str | None = Field(default=None, description="Azure storage account name")
    account_key: str | None = Field(default=None, description="Azure storage account key")
    container: str = Field(default="vcpkg-harbor", description="Azure container name")


class GCSSettings(BaseSettings):
    """Google Cloud Storage backend configuration."""

    model_config = SettingsConfigDict(
        env_prefix="VCPKG_GCS_",
        env_file=".env",
        extra="ignore",
    )

    bucket: str = Field(default="vcpkg-harbor", description="GCS bucket name")
    project: str | None = Field(default=None, description="GCP project ID")
    credentials_file: str | None = Field(
        default=None, description="Path to service account JSON"
    )


class LoggingSettings(BaseSettings):
    """Logging configuration settings."""

    model_config = SettingsConfigDict(
        env_prefix="VCPKG_LOG_",
        env_file=".env",
        extra="ignore",
    )

    level: str = Field(default="INFO", description="Logging level")
    json_format: bool = Field(default=False, alias="json", description="Use JSON format for logs")
    file: str | None = Field(default="logs/vcpkg-harbor.log", description="Log file path")
    retention_days: int = Field(default=30, description="Log retention in days")

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v.upper()


class AuthSettings(BaseSettings):
    """Authentication configuration settings."""

    model_config = SettingsConfigDict(
        env_prefix="VCPKG_AUTH_",
        env_file=".env",
        extra="ignore",
    )

    enabled: bool = Field(default=False, description="Enable authentication")
    type: Literal["none", "basic", "token", "oauth2"] = Field(
        default="none",
        description="Authentication type",
    )
    token: str | None = Field(default=None, description="Static API token for token auth")
    basic_users: str | None = Field(
        default=None,
        description="Comma-separated user:password pairs for basic auth",
    )


class MetricsSettings(BaseSettings):
    """Metrics configuration settings."""

    model_config = SettingsConfigDict(
        env_prefix="VCPKG_METRICS_",
        env_file=".env",
        extra="ignore",
    )

    enabled: bool = Field(default=True, description="Enable Prometheus metrics")
    path: str = Field(default="/metrics", description="Metrics endpoint path")


class DashboardSettings(BaseSettings):
    """Dashboard configuration settings."""

    model_config = SettingsConfigDict(
        env_prefix="VCPKG_DASHBOARD_",
        env_file=".env",
        extra="ignore",
    )

    enabled: bool = Field(default=True, description="Enable web dashboard")
    path: str = Field(default="/", description="Dashboard base path")


class Settings(BaseSettings):
    """Main settings class that aggregates all configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    server: ServerSettings = Field(default_factory=ServerSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    minio: MinioSettings = Field(default_factory=MinioSettings)
    s3: S3Settings = Field(default_factory=S3Settings)
    azure: AzureSettings = Field(default_factory=AzureSettings)
    gcs: GCSSettings = Field(default_factory=GCSSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    metrics: MetricsSettings = Field(default_factory=MetricsSettings)
    dashboard: DashboardSettings = Field(default_factory=DashboardSettings)

    def get_storage_config(self) -> dict:
        """Get the configuration for the active storage backend."""
        backend_configs = {
            "minio": self.minio.model_dump(),
            "filesystem": {"path": self.storage.path},
            "s3": self.s3.model_dump(),
            "azure": self.azure.model_dump(),
            "gcs": self.gcs.model_dump(),
        }
        return backend_configs.get(self.storage.type, {})


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
