"""Storage backend implementations."""
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Optional

import structlog

from app.storage.base import (
    StorageBackend,
    PackageIdentifier,
    PackageMetadata,
    StorageError,
    NotFoundError,
    AlreadyExistsError,
)

logger = structlog.get_logger(__name__)

class FileStorageBackend(StorageBackend):
    """File-based storage backend implementation."""

    def __init__(
        self,
        root_path: Path | str,
        work_dir: Optional[Path | str] = None,
        chunk_size: int = 8192
    ):
        """Initialize the file storage backend.
        
        Args:
            root_path: Root directory for package storage
            work_dir: Working directory for temporary files (default: {root_path}/.work)
            chunk_size: Size of chunks for file operations (default: 8192)
        """
        self.root = Path(root_path).resolve()
        self.work_dir = Path(work_dir) if work_dir else self.root / ".work"
        self.chunk_size = chunk_size

    async def initialize(self) -> None:
        """Initialize storage backend."""
        try:
            # Create root and work directories
            self.root.mkdir(parents=True, exist_ok=True)
            self.work_dir.mkdir(parents=True, exist_ok=True)

            # Test write permissions
            self._validate_permissions()

            logger.info(
                "file_storage_initialized",
                root=str(self.root),
                work_dir=str(self.work_dir)
            )

        except OSError as e:
            raise StorageError(f"Failed to initialize storage: {e}")

    async def cleanup(self) -> None:
        """Clean up any resources."""
        try:
            if self.work_dir.exists():
                shutil.rmtree(self.work_dir)
                self.work_dir.mkdir(parents=True, exist_ok=True)
                logger.info("work_directory_cleaned")
        except OSError as e:
            logger.error("cleanup_failed", error=str(e))
            raise StorageError(f"Failed to clean up: {e}")

    def _validate_permissions(self) -> None:
        """Validate storage permissions."""
        try:
            test_file = self.work_dir / f"test-{os.getpid()}"
            test_content = b"test"

            # Test write
            test_file.write_bytes(test_content)

            # Test read
            content = test_file.read_bytes()
            if content != test_content:
                raise StorageError("Data verification failed")

            # Test delete
            test_file.unlink()

        except OSError as e:
            raise StorageError(f"Permission validation failed: {e}")

    def _get_package_path(self, package: PackageIdentifier) -> Path:
        """Get the full path for a package."""
        return self.root / package.name / package.version / f"{package.sha}.bin"

    def _get_metadata_path(self, package_path: Path) -> Path:
        """Get the metadata file path for a package."""
        return package_path.with_suffix('.meta.json')

    async def get(self, package: PackageIdentifier, writer: BinaryIO) -> None:
        """Get a package from storage."""
        path = self._get_package_path(package)
        if not path.exists():
            raise NotFoundError(f"Package not found: {package}")

        try:
            with path.open('rb') as f:
                while chunk := f.read(self.chunk_size):
                    writer.write(chunk)
            logger.info("package_retrieved", package=str(package))
        except OSError as e:
            logger.error("package_retrieval_failed", package=str(package), error=str(e))
            raise StorageError(f"Failed to read package: {e}")

    async def head(self, package: PackageIdentifier) -> int:
        """Get package size."""
        path = self._get_package_path(package)
        if not path.exists():
            raise NotFoundError(f"Package not found: {package}")

        try:
            return path.stat().st_size
        except OSError as e:
            raise StorageError(f"Failed to get package info: {e}")

    async def exists(self, package: PackageIdentifier) -> bool:
        """Check if a package exists."""
        path = self._get_package_path(package)
        return path.exists()

    async def put(self, package: PackageIdentifier, reader: BinaryIO) -> int:
        """Put a package into storage."""
        final_path = self._get_package_path(package)

        if final_path.exists():
            raise AlreadyExistsError(f"Package already exists: {package}")

        temp_file = None
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(
                dir=self.work_dir,
                prefix=f'pkg-{package.name}-',
                delete=False
            ) as tmp:
                temp_file = Path(tmp.name)
                size = 0

                # Copy data in chunks
                while chunk := reader.read(self.chunk_size):
                    size += len(chunk)
                    tmp.write(chunk)
                tmp.flush()

            # Create parent directory
            final_path.parent.mkdir(parents=True, exist_ok=True)

            # Move file to final location
            shutil.move(temp_file, final_path)

            # Create metadata
            metadata = PackageMetadata(
                name=package.name,
                version=package.version,
                sha=package.sha,
                size=size,
                created_at=datetime.now(timezone.utc).isoformat()
            )
            await self._save_metadata(final_path, metadata)

            logger.info(
                "package_stored",
                package=str(package),
                size=size
            )
            return size

        except OSError as e:
            if temp_file and temp_file.exists():
                temp_file.unlink()
            logger.error("package_storage_failed", package=str(package), error=str(e))
            raise StorageError(f"Failed to store package: {e}")

    async def delete(self, package: PackageIdentifier) -> None:
        """Delete a package."""
        path = self._get_package_path(package)
        if not path.exists():
            raise NotFoundError(f"Package not found: {package}")

        try:
            # Delete package and metadata
            path.unlink()

            # Try to remove empty parent directories
            parent = path.parent
            while parent != self.root:
                try:
                    parent.rmdir()
                    parent = parent.parent
                except OSError:
                    break

            logger.info("package_deleted", package=str(package))
        except OSError as e:
            raise StorageError(f"Failed to delete package: {e}")

    async def _save_metadata(self, package_path: Path, metadata: PackageMetadata) -> None:
        """Save package metadata."""
        import json
        metadata_path = self._get_metadata_path(package_path)
        
        try:
            metadata_dict = metadata.model_dump()
            metadata_path.write_text(json.dumps(metadata_dict, indent=2))
        except OSError as e:
            raise StorageError(f"Failed to save metadata: {e}")

    async def get_metadata(self, package: PackageIdentifier) -> PackageMetadata:
        """Get package metadata."""
        import json
        path = self._get_package_path(package)
        if not path.exists():
            raise NotFoundError(f"Package not found: {package}")

        metadata_path = self._get_metadata_path(path)
        try:
            if metadata_path.exists():
                # Load from metadata file
                data = json.loads(metadata_path.read_text())
                return PackageMetadata(**data)
            else:
                # Create basic metadata from file info
                stats = path.stat()
                return PackageMetadata(
                    name=package.name,
                    version=package.version,
                    sha=package.sha,
                    size=stats.st_size,
                    created_at=datetime.fromtimestamp(
                        stats.st_mtime, timezone.utc
                    ).isoformat()
                )
        except Exception as e:
            raise StorageError(f"Failed to get metadata: {e}")