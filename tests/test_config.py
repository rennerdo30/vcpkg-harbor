"""Tests for configuration system."""

import os

import pytest

from vcpkg_harbor.core.config import (
    LoggingSettings,
    MinioSettings,
    ServerSettings,
    Settings,
    StorageSettings,
)


def test_default_server_settings():
    """Test default server settings."""
    settings = ServerSettings()
    assert settings.host == "0.0.0.0"
    assert settings.port == 15151
    assert settings.workers == 4
    assert settings.read_only is False
    assert settings.write_only is False


def test_default_storage_settings():
    """Test default storage settings."""
    settings = StorageSettings()
    assert settings.type == "filesystem"
    assert settings.path == "./cache"


def test_default_minio_settings():
    """Test default MinIO settings."""
    settings = MinioSettings()
    assert settings.endpoint == "localhost:9000"
    assert settings.bucket == "vcpkg-harbor"
    assert settings.secure is False


def test_logging_level_validation():
    """Test logging level validation."""
    settings = LoggingSettings(level="DEBUG")
    assert settings.level == "DEBUG"

    settings = LoggingSettings(level="info")
    assert settings.level == "INFO"

    with pytest.raises(ValueError):
        LoggingSettings(level="INVALID")


def test_settings_aggregation():
    """Test that Settings aggregates all sub-settings."""
    settings = Settings()
    assert hasattr(settings, "server")
    assert hasattr(settings, "storage")
    assert hasattr(settings, "minio")
    assert hasattr(settings, "logging")
    assert hasattr(settings, "auth")


def test_get_storage_config():
    """Test getting storage config for different backends."""
    settings = Settings()

    # MinIO config
    settings.storage.type = "minio"
    config = settings.get_storage_config()
    assert "endpoint" in config
    assert "bucket" in config

    # Filesystem config
    settings.storage.type = "filesystem"
    config = settings.get_storage_config()
    assert "path" in config
