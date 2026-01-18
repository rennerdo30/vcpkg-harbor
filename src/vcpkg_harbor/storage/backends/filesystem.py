"""Filesystem storage backend implementation."""

import asyncio
import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

import aiofiles
import aiofiles.os
import structlog

from vcpkg_harbor.core.exceptions import (
    PackageAlreadyExistsError,
    PackageNotFoundError,
    StorageError,
)
from vcpkg_harbor.storage.base import PackageInfo

logger = structlog.get_logger(__name__)


class FilesystemBackend:
    """Local filesystem storage backend."""

    def __init__(self, path: str = "./cache") -> None:
        """Initialize filesystem backend.

        Args:
            path: Base path for storing packages
        """
        self.base_path = Path(path).resolve()

    def _get_package_path(self, name: str, version: str, sha: str) -> Path:
        """Get the full path for a package."""
        return self.base_path / name / version / sha

    async def initialize(self) -> None:
        """Initialize the filesystem backend."""
        logger.info("Initializing filesystem backend", path=str(self.base_path))

        try:
            self.base_path.mkdir(parents=True, exist_ok=True)
            logger.debug("Storage directory ready", path=str(self.base_path))
        except Exception as e:
            logger.error("Failed to initialize filesystem backend", error=str(e))
            raise StorageError(f"Failed to initialize filesystem storage: {e}", cause=e)

    async def close(self) -> None:
        """Close the filesystem backend (no-op for filesystem)."""
        logger.debug("Closing filesystem backend")

    async def exists(self, name: str, version: str, sha: str) -> bool:
        """Check if a package exists."""
        package_path = self._get_package_path(name, version, sha)
        return package_path.exists()

    async def get(self, name: str, version: str, sha: str) -> AsyncIterator[bytes]:
        """Get a package as an async iterator of bytes."""
        package_path = self._get_package_path(name, version, sha)
        logger.debug("Getting package", path=str(package_path))

        if not package_path.exists():
            logger.warning("Package not found", path=str(package_path))
            raise PackageNotFoundError(name, version, sha)

        try:
            async with aiofiles.open(package_path, "rb") as f:
                chunk_size = 64 * 1024  # 64KB chunks
                while True:
                    chunk = await f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
        except Exception as e:
            logger.error("Error reading package", path=str(package_path), error=str(e))
            raise StorageError(f"Error reading package: {e}", cause=e)

    async def put(
        self,
        name: str,
        version: str,
        sha: str,
        data: AsyncIterator[bytes],
        size: int | None = None,
    ) -> PackageInfo:
        """Store a package."""
        package_path = self._get_package_path(name, version, sha)
        logger.debug("Putting package", path=str(package_path))

        # Check if already exists
        if package_path.exists():
            logger.warning("Package already exists", path=str(package_path))
            raise PackageAlreadyExistsError(name, version, sha)

        try:
            # Create parent directories
            package_path.parent.mkdir(parents=True, exist_ok=True)

            # Write data to file
            total_size = 0
            hasher = hashlib.md5()

            async with aiofiles.open(package_path, "wb") as f:
                async for chunk in data:
                    await f.write(chunk)
                    total_size += len(chunk)
                    hasher.update(chunk)

            etag = hasher.hexdigest()
            logger.info("Package uploaded", path=str(package_path), size=total_size)

            return PackageInfo(
                name=name,
                version=version,
                sha=sha,
                size=total_size,
                etag=etag,
                created_at=datetime.utcnow(),
            )

        except PackageAlreadyExistsError:
            raise
        except Exception as e:
            # Clean up partial file on error
            if package_path.exists():
                package_path.unlink()
            logger.error("Error uploading package", path=str(package_path), error=str(e))
            raise StorageError(f"Error uploading package: {e}", cause=e)

    async def delete(self, name: str, version: str, sha: str) -> bool:
        """Delete a package."""
        package_path = self._get_package_path(name, version, sha)
        logger.debug("Deleting package", path=str(package_path))

        if not package_path.exists():
            return False

        try:
            await aiofiles.os.remove(package_path)

            # Clean up empty parent directories
            await self._cleanup_empty_dirs(package_path.parent)

            logger.info("Package deleted", path=str(package_path))
            return True
        except Exception as e:
            logger.error("Error deleting package", path=str(package_path), error=str(e))
            raise StorageError(f"Error deleting package: {e}", cause=e)

    async def _cleanup_empty_dirs(self, path: Path) -> None:
        """Remove empty parent directories up to base path."""
        try:
            while path != self.base_path and path.exists():
                if any(path.iterdir()):
                    break
                path.rmdir()
                path = path.parent
        except Exception:
            pass  # Ignore cleanup errors

    async def stat(self, name: str, version: str, sha: str) -> PackageInfo:
        """Get package information."""
        package_path = self._get_package_path(name, version, sha)

        if not package_path.exists():
            raise PackageNotFoundError(name, version, sha)

        try:
            stat = package_path.stat()

            # Calculate MD5 for etag
            hasher = hashlib.md5()
            async with aiofiles.open(package_path, "rb") as f:
                while chunk := await f.read(64 * 1024):
                    hasher.update(chunk)

            return PackageInfo(
                name=name,
                version=version,
                sha=sha,
                size=stat.st_size,
                etag=hasher.hexdigest(),
                created_at=datetime.fromtimestamp(stat.st_ctime),
            )

        except PackageNotFoundError:
            raise
        except Exception as e:
            raise StorageError(f"Error getting package info: {e}", cause=e)

    async def list_packages(
        self,
        prefix: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[PackageInfo]:
        """List packages in storage."""
        logger.debug("Listing packages", prefix=prefix, limit=limit, offset=offset)

        packages = []
        count = 0

        try:
            # Walk directory structure: base/name/version/sha
            for name_dir in sorted(self.base_path.iterdir()):
                if not name_dir.is_dir():
                    continue

                # Apply prefix filter
                if prefix and not name_dir.name.startswith(prefix.split("/")[0]):
                    continue

                for version_dir in sorted(name_dir.iterdir()):
                    if not version_dir.is_dir():
                        continue

                    for sha_file in sorted(version_dir.iterdir()):
                        if not sha_file.is_file():
                            continue

                        count += 1
                        if count <= offset:
                            continue

                        stat = sha_file.stat()
                        packages.append(
                            PackageInfo(
                                name=name_dir.name,
                                version=version_dir.name,
                                sha=sha_file.name,
                                size=stat.st_size,
                                created_at=datetime.fromtimestamp(stat.st_ctime),
                            )
                        )

                        if limit and len(packages) >= limit:
                            return packages

            return packages

        except Exception as e:
            logger.error("Error listing packages", error=str(e))
            raise StorageError(f"Error listing packages: {e}", cause=e)

    async def get_stats(self) -> dict:
        """Get storage statistics."""
        try:
            packages = await self.list_packages()
            total_size = sum(p.size for p in packages)
            package_names = set(p.name for p in packages)

            # Get disk usage
            stat = os.statvfs(self.base_path)
            disk_free = stat.f_frsize * stat.f_bavail
            disk_total = stat.f_frsize * stat.f_blocks

            return {
                "total_packages": len(packages),
                "total_size_bytes": total_size,
                "unique_package_names": len(package_names),
                "backend": "filesystem",
                "path": str(self.base_path),
                "disk_free_bytes": disk_free,
                "disk_total_bytes": disk_total,
            }
        except Exception as e:
            logger.error("Error getting stats", error=str(e))
            return {
                "error": str(e),
                "backend": "filesystem",
            }

    async def health_check(self) -> bool:
        """Check if filesystem storage is healthy."""
        try:
            # Check if directory exists and is writable
            test_file = self.base_path / ".health_check"
            test_file.write_text("ok")
            test_file.unlink()
            return True
        except Exception as e:
            logger.warning("Health check failed", error=str(e))
            return False
