import os
import shutil
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from minio import Minio
from minio.error import S3Error

from app.core.config import Settings, MinioStorageSettings, FileStorageSettings
from app.storage.base import PackageIdentifier, StorageBackend
from app.storage.file import FileStorageBackend
from app.storage.minio import MinioStorageBackend


# Test data
@pytest.fixture
def sample_package() -> PackageIdentifier:
    """Sample package identifier for testing."""
    return PackageIdentifier(
        name="test-package",
        version="1.0.0",
        sha="abcdef123456"
    )

@pytest.fixture
def sample_data() -> bytes:
    """Sample binary data for testing."""
    return b"This is test package data" * 1024  # ~24KB of data

# File storage fixtures
@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for testing."""
    temp_path = tempfile.mkdtemp(prefix="vcpkg-harbor-test-")
    try:
        yield Path(temp_path)
    finally:
        shutil.rmtree(temp_path, ignore_errors=True)

@pytest.fixture
async def file_storage(temp_dir: Path) -> AsyncGenerator[FileStorageBackend, None]:
    """Create a file storage backend for testing."""
    storage = FileStorageBackend(
        root_path=temp_dir / "packages",
        work_dir=temp_dir / "work"
    )
    await storage.initialize()
    try:
        yield storage
    finally:
        await storage.cleanup()

# MinIO storage fixtures
@pytest.fixture
def minio_client(temp_dir: Path) -> Generator[Minio, None, None]:
    """Create a MinIO client mock for testing."""
    client = MagicMock(spec=Minio)
    
    # Setup basic mocked behavior
    client.bucket_exists.return_value = True
    
    # Storage for "uploaded" objects
    storage_dir = temp_dir / "minio"
    storage_dir.mkdir(exist_ok=True)
    
    def mock_put_object(bucket_name: str, object_name: str, data, length: int, **kwargs):
        object_path = storage_dir / object_name
        object_path.parent.mkdir(parents=True, exist_ok=True)
        with open(object_path, 'wb') as f:
            f.write(data.read())
    
    def mock_get_object(bucket_name: str, object_name: str, **kwargs):
        object_path = storage_dir / object_name
        if not object_path.exists():
            raise S3Error(code='NoSuchKey', message="Object does not exist")
        return open(object_path, 'rb')
    
    def mock_remove_object(bucket_name: str, object_name: str):
        object_path = storage_dir / object_name
        if not object_path.exists():
            raise S3Error(code='NoSuchKey', message="Object does not exist")
        object_path.unlink()
    
    # Attach mock methods
    client.put_object.side_effect = mock_put_object
    client.get_object.side_effect = mock_get_object
    client.remove_object.side_effect = mock_remove_object
    
    yield client

@pytest.fixture
async def minio_storage(minio_client: Minio) -> AsyncGenerator[MinioStorageBackend, None]:
    """Create a MinIO storage backend for testing."""
    storage = MinioStorageBackend(
        endpoint="localhost:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        bucket="test-bucket",
        secure=False
    )
    # Replace real client with mock
    storage.client = minio_client
    
    await storage.initialize()
    try:
        yield storage
    finally:
        await storage.cleanup()

# FastAPI test client fixtures
@pytest.fixture
def test_settings(temp_dir: Path) -> Settings:
    """Create test settings."""
    return Settings(
        storage_type="file",
        file_storage=FileStorageSettings(
            path=temp_dir / "packages"
        ),
        minio_storage=MinioStorageSettings(
            endpoint="localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            bucket="test-bucket",
            secure=False
        )
    )

@pytest.fixture
def test_client(test_settings: Settings) -> Generator[TestClient, None, None]:
    """Create FastAPI test client."""
    from app.main import create_app
    app = create_app(test_settings)
    with TestClient(app) as client:
        yield client

# Storage backend fixtures for different configurations
@pytest.fixture
async def storage_backend(
    request: pytest.FixtureRequest,
    file_storage: FileStorageBackend,
    minio_storage: MinioStorageBackend
) -> AsyncGenerator[StorageBackend, None]:
    """Parameterized storage backend fixture."""
    backend_type = request.param if hasattr(request, 'param') else "file"
    if backend_type == "file":
        yield file_storage
    elif backend_type == "minio":
        yield minio_storage
    else:
        raise ValueError(f"Unknown storage backend type: {backend_type}")

# Utility fixtures
@pytest.fixture
def cleanup_temp_files() -> Generator[None, None, None]:
    """Cleanup temporary files after tests."""
    temp_files = []
    
    def register_temp_file(path: str | Path):
        temp_files.append(Path(path))
    
    yield register_temp_file
    
    for path in temp_files:
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)

# Helper functions for tests
def assert_files_equal(path1: Path, path2: Path) -> bool:
    """Assert that two files have the same content."""
    with open(path1, 'rb') as f1, open(path2, 'rb') as f2:
        while chunk1 := f1.read(8192):
            chunk2 = f2.read(8192)
            if chunk1 != chunk2:
                return False
        return f2.read() == b""  # Check if second file has no remaining data

def create_temp_package(
    storage: StorageBackend,
    package: PackageIdentifier,
    data: bytes
) -> None:
    """Create a temporary package in storage."""
    import io
    stream = io.BytesIO(data)
    return storage.put(package, stream)