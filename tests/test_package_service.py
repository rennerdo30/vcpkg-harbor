"""Tests for package service."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, Mock

from vcpkg_harbor.services.package_service import PackageService, PackageVersion, PackageSummary
from vcpkg_harbor.storage.base import PackageInfo


@pytest.fixture
def mock_storage():
    return AsyncMock()


@pytest.fixture
def package_service(mock_storage):
    return PackageService(mock_storage)


async def test_package_version_structure():
    """Test that PackageVersion includes the triplet field."""
    now = datetime.now()
    info = PackageInfo(
        name="test-pkg",
        version="1.0.0",
        sha="abc123456",
        triplet="x64-linux",
        size=1024,
        created_at=now
    )
    
    version = PackageVersion.from_package_info(info)
    
    assert version.name == "test-pkg"
    assert version.version == "1.0.0"
    assert version.sha == "abc123456"
    assert version.triplet == "x64-linux"
    assert version.size == 1024
    assert version.created_at == now.isoformat()


async def test_get_package_versions(package_service, mock_storage):
    """Test get_package_versions returns versions with triplets."""
    mock_storage.list_packages.return_value = [
        PackageInfo(
            name="test-pkg",
            version="1.0.0",
            sha="sha1",
            triplet="x64-linux",
            size=100
        ),
        PackageInfo(
            name="test-pkg",
            version="1.0.0",
            sha="sha1",
            triplet="x64-windows",
            size=100
        )
    ]
    
    versions = await package_service.get_package_versions("test-pkg")
    
    assert len(versions) == 2
    assert versions[0].triplet in ["x64-linux", "x64-windows"]
    assert versions[1].triplet in ["x64-linux", "x64-windows"]
    assert versions[0].triplet != versions[1].triplet
