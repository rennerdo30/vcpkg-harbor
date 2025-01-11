import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Optional, List, Dict, Any
import contextlib
import json

import structlog
from app.core.config import settings
from app.storage.base import (
    BaseStorageBackend,
    PackageIdentifier,
    PackageMetadata,
    StorageError,
    NotFoundError,
    AlreadyExistsError,
    StorageWriteError,
    StorageReadError,
)

logger = structlog.get_logger(__name__)

class FileStorageBackend(BaseStorageBackend):
    """File-based storage backend implementation."""

    def __init__(
        self,
        root_path: Path | str,
        work_dir: Optional[Path | str] = None,
        chunk_size: int = 8192,
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
        self.metadata_suffix = ".meta.json"

    async def initialize(self) -> None:
        """Initialize the storage backend."""
        await super().initialize()
        try:
            # Create root and work directories
            self.root.mkdir(parents=True, exist_ok=True)
            self.work_dir.mkdir(parents=True, exist_ok=True)

            # Validate permissions with a test file
            self._validate_permissions()

            logger.info(
                "file_storage_initialized",
                root=str(self.root),
                work_dir=str(self.work_dir)
            )

        except OSError as e:
            raise StorageError(f"Failed to initialize storage: {e}")

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
        return self.root / package.get_path()

    def _get_metadata_path(self, package_path: Path) -> Path:
        """Get the metadata file path for a package."""
        return package_path.with_suffix(self.metadata_suffix)

    async def get(self, package: PackageIdentifier, writer: BinaryIO) -> None:
        """Get a package from storage."""
        self._validate_package(package)
        path = self._get_package_path(package)

        if not path.exists():
            raise NotFoundError(f"Package not found: {package}")

        try:
            with path.open('rb') as f:
                while chunk := f.read(self.chunk_size):
                    writer.write(chunk)
            logger.info("package_retrieved", package=str(package), path=str(path))

        except OSError as e:
            logger.error(
                "package_retrieval_failed",
                package=str(package),
                path=str(path),
                error=str(e)
            )
            raise StorageReadError(f"Failed to read package: {e}")

    async def put(self, package: PackageIdentifier, reader: BinaryIO) -> int:
        """Put a package into storage."""
        self._validate_package(package)
        final_path = self._get_package_path(package)

        if final_path.exists():
            raise AlreadyExistsError(f"Package already exists: {package}")

        temp_path = None
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(
                dir=self.work_dir,
                prefix=f'pkg-{package.name}-',
                delete=False
            ) as tmp:
                temp_path = Path(tmp.name)
                size = 0

                # Copy data in chunks
                while chunk := reader.read(self.chunk_size):
                    size += len(chunk)
                    tmp.write(chunk)
                tmp.flush()

            # Ensure parent directory exists
            final_path.parent.mkdir(parents=True, exist_ok=True)

            # Move file to final location
            shutil.move(temp_path, final_path)

            # Create metadata
            metadata = PackageMetadata(
                name=package.name,
                version=package.version,
                sha=package.sha,
                size=size,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            await self._save_metadata(final_path, metadata)

            logger.info(
                "package_stored",
                package=str(package),
                path=str(final_path),
                size=size
            )
            return size

        except OSError as e:
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)
            logger.error(
                "package_storage_failed",
                package=str(package),
                error=str(e)
            )
            raise StorageWriteError(f"Failed to store package: {e}")

    async def exists(self, package: PackageIdentifier) -> bool:
        """Check if a package exists."""
        self._validate_package(package)
        path = self._get_package_path(package)
        return path.exists()

    async def delete(self, package: PackageIdentifier) -> None:
        """Delete a package."""
        self._validate_package(package)
        path = self._get_package_path(package)
        metadata_path = self._get_metadata_path(path)

        if not path.exists():
            raise NotFoundError(f"Package not found: {package}")

        try:
            # Delete package and metadata
            path.unlink()
            metadata_path.unlink(missing_ok=True)

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
            logger.error(
                "package_deletion_failed",
                package=str(package),
                error=str(e)
            )
            raise StorageError(f"Failed to delete package: {e}")

    async def _save_metadata(self, package_path: Path, metadata: PackageMetadata) -> None:
        """Save package metadata."""
        metadata_path = self._get_metadata_path(package_path)
        try:
            metadata_dict = {
                'name': metadata.name,
                'version': metadata.version,
                'sha': metadata.sha,
                'size': metadata.size,
                'created_at': metadata.created_at,
                'content_type': metadata.content_type,
                'extra': metadata.extra or {},
            }
            metadata_path.write_text(json.dumps(metadata_dict, indent=2))
        except OSError as e:
            raise StorageError(f"Failed to save metadata: {e}")

    async def get_metadata(self, package: PackageIdentifier) -> PackageMetadata:
        """Get package metadata."""
        self._validate_package(package)
        path = self._get_package_path(package)
        metadata_path = self._get_metadata_path(path)

        if not path.exists():
            raise NotFoundError(f"Package not found: {package}")

        try:
            if metadata_path.exists():
                # Load from metadata file
                metadata_dict = json.loads(metadata_path.read_text())
                return PackageMetadata(**metadata_dict)
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
                    ).isoformat(),
                )

        except (OSError, json.JSONDecodeError) as e:
            raise StorageError(f"Failed to get metadata: {e}")

    async def list_versions(self, name: str, version: str) -> List[PackageIdentifier]:
        """List all packages for a specific version."""
        version_dir = self.root / name / version
        if not version_dir.exists():
            return []

        try:
            packages = []
            for path in version_dir.glob("*"):
                if path.is_file() and not path.name.endswith(self.metadata_suffix):
                    packages.append(PackageIdentifier(
                        name=name,
                        version=version,
                        sha=path.stem
                    ))
            return packages

        except OSError as e:
            raise StorageError(f"Failed to list versions: {e}")

    async def list_all_versions(self, name: str) -> List[str]:
        """List all versions of a package."""
        package_dir = self.root / name
        if not package_dir.exists():
            return []

        try:
            versions = []
            for path in package_dir.iterdir():
                if path.is_dir():
                    versions.append(path.name)
            return sorted(versions)

        except OSError as e:
            raise StorageError(f"Failed to list all versions: {e}")

    async def cleanup(self) -> None:
        """Clean up temporary resources."""
        try:
            # Remove all files in work directory
            if self.work_dir.exists():
                for path in self.work_dir.iterdir():
                    if path.is_file():
                        path.unlink(missing_ok=True)
            logger.info("storage_cleaned_up")

        except OSError as e:
            logger.error("cleanup_failed", error=str(e))
            raise StorageError(f"Failed to clean up: {e}")