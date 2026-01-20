"""Cache service for handling package operations."""

from typing import TYPE_CHECKING, AsyncIterator

import structlog

from vcpkg_harbor.core.exceptions import (
    PackageAlreadyExistsError,
    PackageNotFoundError,
    StorageError,
)
from vcpkg_harbor.storage.base import PackageInfo

if TYPE_CHECKING:
    from vcpkg_harbor.core.config import Settings
    from vcpkg_harbor.storage.base import StorageBackend

logger = structlog.get_logger(__name__)


class CacheService:
    """Service for managing the package cache."""

    def __init__(self, storage: "StorageBackend", settings: "Settings") -> None:
        """Initialize the cache service.

        Args:
            storage: Storage backend instance
            settings: Application settings
        """
        self.storage = storage
        self.settings = settings
        self._read_only = settings.server.read_only
        self._write_only = settings.server.write_only

    async def check_exists(self, name: str, version: str, sha: str, triplet: str) -> bool:
        """Check if a package exists in the cache.

        Args:
            name: Package name
            version: Package version
            sha: Package SHA hash
            triplet: Target triplet (e.g., x64-linux, x64-windows)

        Returns:
            True if package exists, False otherwise
        """
        logger.debug("Checking package existence", name=name, version=version, sha=sha, triplet=triplet)

        try:
            exists = await self.storage.exists(name, version, sha, triplet)
            if exists:
                logger.info("Package exists", name=name, version=version, sha=sha, triplet=triplet)
            else:
                logger.info("Package not found", name=name, version=version, sha=sha, triplet=triplet)
            return exists
        except Exception as e:
            logger.error(
                "Error checking package existence",
                name=name,
                version=version,
                sha=sha,
                triplet=triplet,
                error=str(e),
            )
            raise StorageError(f"Error checking package existence: {e}", cause=e)

    async def get_package(
        self, name: str, version: str, sha: str, triplet: str
    ) -> AsyncIterator[bytes]:
        """Get a package from the cache.

        Args:
            name: Package name
            version: Package version
            sha: Package SHA hash
            triplet: Target triplet (e.g., x64-linux, x64-windows)

        Yields:
            Package data chunks

        Raises:
            PackageNotFoundError: If the package doesn't exist
            StorageError: If there's an error retrieving the package
        """
        if self._write_only:
            logger.warning(
                "Read operation blocked in write-only mode",
                name=name,
                version=version,
                sha=sha,
                triplet=triplet,
            )
            raise PackageNotFoundError(name, version, sha, triplet)

        logger.info("Downloading package", name=name, version=version, sha=sha, triplet=triplet)

        try:
            async for chunk in self.storage.get(name, version, sha, triplet):
                yield chunk
            logger.info("Package download complete", name=name, version=version, sha=sha, triplet=triplet)
        except PackageNotFoundError:
            logger.warning("Package not found", name=name, version=version, sha=sha, triplet=triplet)
            raise
        except Exception as e:
            logger.error(
                "Error downloading package",
                name=name,
                version=version,
                sha=sha,
                triplet=triplet,
                error=str(e),
            )
            raise StorageError(f"Error downloading package: {e}", cause=e)

    async def put_package(
        self,
        name: str,
        version: str,
        sha: str,
        triplet: str,
        data: AsyncIterator[bytes],
        size: int | None = None,
    ) -> PackageInfo:
        """Store a package in the cache.

        Args:
            name: Package name
            version: Package version
            sha: Package SHA hash
            triplet: Target triplet (e.g., x64-linux, x64-windows)
            data: Async iterator of package data
            size: Optional total size of the package

        Returns:
            PackageInfo with details about the stored package

        Raises:
            PackageAlreadyExistsError: If the package already exists
            StorageError: If there's an error storing the package
        """
        if self._read_only:
            logger.warning(
                "Write operation blocked in read-only mode",
                name=name,
                version=version,
                sha=sha,
                triplet=triplet,
            )
            raise StorageError("Server is in read-only mode")

        logger.info("Uploading package", name=name, version=version, sha=sha, triplet=triplet, size=size)

        try:
            package_info = await self.storage.put(name, version, sha, triplet, data, size)
            logger.info(
                "Package uploaded successfully",
                name=name,
                version=version,
                sha=sha,
                triplet=triplet,
                size=package_info.size,
            )
            return package_info
        except PackageAlreadyExistsError:
            logger.warning("Package already exists", name=name, version=version, sha=sha, triplet=triplet)
            raise
        except Exception as e:
            logger.error(
                "Error uploading package",
                name=name,
                version=version,
                sha=sha,
                triplet=triplet,
                error=str(e),
            )
            raise StorageError(f"Error uploading package: {e}", cause=e)

    async def delete_package(self, name: str, version: str, sha: str, triplet: str) -> bool:
        """Delete a package from the cache.

        Args:
            name: Package name
            version: Package version
            sha: Package SHA hash
            triplet: Target triplet (e.g., x64-linux, x64-windows)

        Returns:
            True if package was deleted, False if it didn't exist

        Raises:
            StorageError: If there's an error deleting the package
        """
        if self._read_only:
            logger.warning(
                "Delete operation blocked in read-only mode",
                name=name,
                version=version,
                sha=sha,
                triplet=triplet,
            )
            raise StorageError("Server is in read-only mode")

        logger.info("Deleting package", name=name, version=version, sha=sha, triplet=triplet)

        try:
            deleted = await self.storage.delete(name, version, sha, triplet)
            if deleted:
                logger.info("Package deleted", name=name, version=version, sha=sha, triplet=triplet)
            else:
                logger.info("Package not found for deletion", name=name, version=version, sha=sha, triplet=triplet)
            return deleted
        except Exception as e:
            logger.error(
                "Error deleting package",
                name=name,
                version=version,
                sha=sha,
                triplet=triplet,
                error=str(e),
            )
            raise StorageError(f"Error deleting package: {e}", cause=e)

    async def get_package_info(self, name: str, version: str, sha: str, triplet: str) -> PackageInfo:
        """Get package information without downloading.

        Args:
            name: Package name
            version: Package version
            sha: Package SHA hash
            triplet: Target triplet (e.g., x64-linux, x64-windows)

        Returns:
            PackageInfo with package metadata

        Raises:
            PackageNotFoundError: If the package doesn't exist
        """
        return await self.storage.stat(name, version, sha, triplet)
