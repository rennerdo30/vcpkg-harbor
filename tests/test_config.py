"""Tests for configuration system."""

import os
from unittest import mock

import pytest

from vcpkg_harbor.core.config import (
    DEFAULT_NAMESPACE,
    DEFAULT_TAG_PATTERN,
    LoggingSettings,
    MinioSettings,
    ServerSettings,
    Settings,
    StorageSettings,
    TagSettings,
)


def test_default_server_settings():
    """Test default server settings."""
    settings = ServerSettings(_env_file=None)
    assert settings.host == "0.0.0.0"
    assert settings.port == 15151
    assert settings.workers == 4
    assert settings.read_only is False
    assert settings.write_only is False


@mock.patch.dict(os.environ, {}, clear=True)
def test_default_storage_settings():
    """Test default storage settings."""
    settings = StorageSettings(_env_file=None)
    assert settings.type == "filesystem"
    assert settings.path == "./cache"


def test_default_minio_settings():
    """Test default MinIO settings."""
    settings = MinioSettings(_env_file=None)
    assert settings.endpoint == "localhost:9000"
    assert settings.bucket == "vcpkg-harbor"
    assert settings.secure is False


def test_logging_level_validation():
    """Test logging level validation."""
    settings = LoggingSettings(level="DEBUG", _env_file=None)
    assert settings.level == "DEBUG"

    settings = LoggingSettings(level="info", _env_file=None)
    assert settings.level == "INFO"

    with pytest.raises(ValueError):
        LoggingSettings(level="INVALID", _env_file=None)


def test_settings_aggregation():
    """Test that Settings aggregates all sub-settings."""
    settings = Settings(_env_file=None)
    assert hasattr(settings, "server")
    assert hasattr(settings, "storage")
    assert hasattr(settings, "minio")
    assert hasattr(settings, "logging")
    assert hasattr(settings, "auth")
    assert hasattr(settings, "tags")


@mock.patch.dict(os.environ, {}, clear=True)
def test_default_tag_settings():
    """Test default build tag settings."""
    settings = TagSettings(_env_file=None)
    assert settings.enabled is True
    assert settings.dedupe is True
    assert settings.allowed is None
    assert settings.allowlist == frozenset()
    assert settings.pattern == DEFAULT_TAG_PATTERN
    assert settings.default_namespace == DEFAULT_NAMESPACE
    assert settings.max_packages_per_tag == 0
    assert settings.max_bytes_per_tag == 0


@mock.patch.dict(
    os.environ,
    {
        "VCPKG_TAGS_ENABLED": "false",
        "VCPKG_TAGS_ALLOWED": "nightly, release ,",
        "VCPKG_TAGS_DEDUPE": "false",
        "VCPKG_TAGS_DEFAULT_NAMESPACE": "_shared",
        "VCPKG_TAGS_MAX_PACKAGES_PER_TAG": "25",
        "VCPKG_TAGS_MAX_BYTES_PER_TAG": "1024",
    },
    clear=True,
)
def test_tag_settings_from_environment():
    """Test that build tag settings are read from VCPKG_TAGS_* variables."""
    settings = TagSettings(_env_file=None)
    assert settings.enabled is False
    assert settings.dedupe is False
    assert settings.allowlist == frozenset({"nightly", "release"})
    assert settings.default_namespace == "_shared"
    assert settings.max_packages_per_tag == 25
    assert settings.max_bytes_per_tag == 1024


def test_tag_pattern_must_compile():
    """Test that an invalid tag pattern is rejected."""
    with pytest.raises(ValueError):
        TagSettings(pattern="[unclosed", _env_file=None)


def test_default_namespace_must_be_a_single_segment():
    """Test that the default namespace cannot contain path separators."""
    with pytest.raises(ValueError):
        TagSettings(default_namespace="a/b", _env_file=None)
    with pytest.raises(ValueError):
        TagSettings(default_namespace="", _env_file=None)


def test_retention_limits_cannot_be_negative():
    """Test that retention limits are non-negative."""
    with pytest.raises(ValueError):
        TagSettings(max_packages_per_tag=-1, _env_file=None)


def test_get_storage_config():
    """Test getting storage config for different backends."""
    settings = Settings(_env_file=None)

    # MinIO config
    settings.storage.type = "minio"
    config = settings.get_storage_config()
    assert "endpoint" in config
    assert "bucket" in config

    # Filesystem config
    settings.storage.type = "filesystem"
    config = settings.get_storage_config()
    assert "path" in config
