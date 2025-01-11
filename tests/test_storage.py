import io
import os
import pytest
from pathlib import Path
from datetime import datetime, timezone

from app.storage.base import (
    PackageIdentifier,
    PackageMetadata,
    StorageError,
    NotFoundError,
    AlreadyExistsError,
)

# Mark all tests as async
pytestmark = pytest.mark.asyncio

@pytest.mark.parametrize("storage_backend", ["file", "minio"], indirect=True)
class TestStorageBackend:
    """Test storage backend implementations."""

    async def test_initialization(self, storage_backend):
        """Test storage initialization."""
        # Should already be initialized by fixture
        assert storage_backend is not None

    async def test_basic_operations(
        self,
        storage_backend,
        sample_package: PackageIdentifier,
        sample_data: bytes
    ):
        """Test basic storage operations."""
        # Check non-existence
        assert not await storage_backend.exists(sample_package)
        
        # Put package
        data_stream = io.BytesIO(sample_data)
        size = await storage_backend.put(sample_package, data_stream)
        assert size == len(sample_data)
        
        # Check existence
        assert await storage_backend.exists(sample_package)
        
        # Get package
        output = io.BytesIO()
        await storage_backend.get(sample_package, output)
        assert output.getvalue() == sample_data
        
        # Delete package
        await storage_backend.delete(sample_package)
        assert not await storage_backend.exists(sample_package)

    async def test_duplicate_package(
        self,
        storage_backend,
        sample_package: PackageIdentifier,
        sample_data: bytes
    ):
        """Test handling of duplicate packages."""
        # First upload should succeed
        await storage_backend.put(sample_package, io.BytesIO(sample_data))
        
        # Second upload should fail
        with pytest.raises(AlreadyExistsError):
            await storage_backend.put(sample_package, io.BytesIO(sample_data))

    async def test_non_existent_package(
        self,
        storage_backend,
        sample_package: PackageIdentifier
    ):
        """Test handling of non-existent packages."""
        with pytest.raises(NotFoundError):
            output = io.BytesIO()
            await storage_backend.get(sample_package, output)

    async def test_delete_non_existent(
        self,
        storage_backend,
        sample_package: PackageIdentifier
    ):
        """Test deleting a non-existent package."""
        with pytest.raises(NotFoundError):
            await storage_backend.delete(sample_package)

    async def test_large_package(self, storage_backend, tmp_path: Path):
        """Test handling of large packages."""
        large_size = 5 * 1024 * 1024  # 5MB
        large_data = os.urandom(large_size)
        package = PackageIdentifier(
            name="large-package",
            version="1.0.0",
            sha="sha256"
        )
        
        # Upload large package
        size = await storage_backend.put(package, io.BytesIO(large_data))
        assert size == large_size
        
        # Download and verify
        output = io.BytesIO()
        await storage_backend.get(package, output)
        assert output.getvalue() == large_data

    async def test_metadata_handling(
        self,
        storage_backend,
        sample_package: PackageIdentifier,
        sample_data: bytes
    ):
        """Test package metadata handling."""
        # Store package
        await storage_backend.put(sample_package, io.BytesIO(sample_data))
        
        # Get metadata
        metadata = await storage_backend.get_metadata(sample_package)
        assert isinstance(metadata, PackageMetadata)
        assert metadata.name == sample_package.name
        assert metadata.version == sample_package.version
        assert metadata.sha == sample_package.sha
        assert metadata.size == len(sample_data)
        assert metadata.content_type == "application/octet-stream"
        
        # Verify timestamp is recent
        created_dt = datetime.fromisoformat(metadata.created_at.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        assert (now - created_dt).total_seconds() < 60

    async def test_version_listing(
        self,
        storage_backend,
        sample_data: bytes
    ):
        """Test version listing functionality."""
        # Create test packages
        packages = [
            PackageIdentifier("test-pkg", "1.0.0", "sha1"),
            PackageIdentifier("test-pkg", "1.0.0", "sha2"),
            PackageIdentifier("test-pkg", "1.0.1", "sha3"),
            PackageIdentifier("other-pkg", "2.0.0", "sha4"),
        ]
        
        for pkg in packages:
            await storage_backend.put(pkg, io.BytesIO(sample_data))
        
        try:
            # List versions for specific package
            versions = await storage_backend.list_all_versions("test-pkg")
            assert len(versions) == 2
            assert "1.0.0" in versions
            assert "1.0.1" in versions
            
            # List packages for specific version
            v1_packages = await storage_backend.list_versions("test-pkg", "1.0.0")
            assert len(v1_packages) == 2
            assert any(p.sha == "sha1" for p in v1_packages)
            assert any(p.sha == "sha2" for p in v1_packages)
        except NotImplementedError:
            pytest.skip("Version listing not supported by this backend")

    @pytest.mark.parametrize("invalid_package", [
        PackageIdentifier("", "1.0.0", "sha1"),  # Empty name
        PackageIdentifier("test", "", "sha1"),    # Empty version
        PackageIdentifier("test", "1.0.0", ""),   # Empty sha
        PackageIdentifier("../test", "1.0.0", "sha1"),  # Path traversal
        PackageIdentifier("test\x00", "1.0.0", "sha1"),  # Null byte
    ])
    async def test_invalid_packages(
        self,
        storage_backend,
        invalid_package: PackageIdentifier,
        sample_data: bytes
    ):
        """Test handling of invalid package identifiers."""
        with pytest.raises((ValueError, StorageError)):
            await storage_backend.put(invalid_package, io.BytesIO(sample_data))

    async def test_concurrent_operations(
        self,
        storage_backend,
        sample_data: bytes
    ):
        """Test concurrent storage operations."""
        import asyncio
        
        async def store_and_retrieve(name: str) -> bool:
            pkg = PackageIdentifier(name, "1.0.0", "sha1")
            await storage_backend.put(pkg, io.BytesIO(sample_data))
            output = io.BytesIO()
            await storage_backend.get(pkg, output)
            return output.getvalue() == sample_data
        
        # Run multiple operations concurrently
        package_names = [f"concurrent-{i}" for i in range(5)]
        results = await asyncio.gather(
            *[store_and_retrieve(name) for name in package_names]
        )
        assert all(results)

    async def test_cleanup(
        self,
        storage_backend,
        sample_package: PackageIdentifier,
        sample_data: bytes
    ):
        """Test storage cleanup."""
        # Store a package
        await storage_backend.put(sample_package, io.BytesIO(sample_data))
        
        # Clean up
        await storage_backend.cleanup()
        
        # Package should still be accessible
        assert await storage_backend.exists(sample_package)
        output = io.BytesIO()
        await storage_backend.get(sample_package, output)
        assert output.getvalue() == sample_data

    @pytest.mark.parametrize("chunk_size", [1024, 8192, 16384])
    async def test_streaming_operations(
        self,
        storage_backend,
        sample_package: PackageIdentifier,
        chunk_size: int
    ):
        """Test streaming operations with different chunk sizes."""
        # Create test data
        data_size = chunk_size * 10
        test_data = os.urandom(data_size)
        
        # Create stream that reads in chunks
        class ChunkedReader:
            def __init__(self, data: bytes, chunk_size: int):
                self.data = data
                self.chunk_size = chunk_size
                self.position = 0
            
            def read(self, size: int = None) -> bytes:
                if size is None:
                    size = self.chunk_size
                if self.position >= len(self.data):
                    return b""
                chunk = self.data[self.position:self.position + size]
                self.position += size
                return chunk
        
        # Upload with chunked reading
        reader = ChunkedReader(test_data, chunk_size)
        size = await storage_backend.put(sample_package, reader)
        assert size == data_size
        
        # Download and verify
        output = io.BytesIO()
        await storage_backend.get(sample_package, output)
        assert output.getvalue() == test_data

# Storage-specific tests
class TestFileStorage:
    """Test file storage specific functionality."""
    
    async def test_work_directory_cleanup(self, file_storage, sample_data: bytes):
        """Test work directory cleanup."""
        work_files_before = list(file_storage.work_dir.glob("*"))
        
        # Store some packages
        for i in range(3):
            pkg = PackageIdentifier(f"test-{i}", "1.0.0", "sha1")
            await file_storage.put(pkg, io.BytesIO(sample_data))
        
        # Cleanup should remove work files but keep packages
        await file_storage.cleanup()
        work_files_after = list(file_storage.work_dir.glob("*"))
        assert len(work_files_after) <= len(work_files_before)

class TestMinioStorage:
    """Test MinIO storage specific functionality."""
    
    async def test_bucket_operations(self, minio_storage):
        """Test MinIO bucket operations."""
        # Bucket should exist after initialization
        assert minio_storage.client.bucket_exists(minio_storage.bucket)

    async def test_client_retries(
        self,
        minio_storage,
        sample_package: PackageIdentifier,
        sample_data: bytes
    ):
        """Test MinIO client retry behavior."""
        # Simulate temporary failure
        original_put = minio_storage.client.put_object
        fail_count = 0
        
        def failing_put(*args, **kwargs):
            nonlocal fail_count
            if fail_count < 2:
                fail_count += 1
                raise ConnectionError("Temporary failure")
            return original_put(*args, **kwargs)
        
        minio_storage.client.put_object = failing_put
        
        # Should succeed after retries
        await minio_storage.put(sample_package, io.BytesIO(sample_data))
        assert await minio_storage.exists(sample_package)