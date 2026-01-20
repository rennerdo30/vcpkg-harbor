"""Base storage protocol for vcpkg-harbor storage backends."""

from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator, Protocol, runtime_checkable


@dataclass
class PackageInfo:
    """Information about a cached package."""

    name: str
    version: str
    sha: str
    triplet: str
    size: int
    etag: str | None = None
    content_type: str = "application/octet-stream"
    created_at: datetime | None = None
    metadata: dict | None = None

    @property
    def object_path(self) -> str:
        """Get the storage object path."""
        return f"{self.name}/{self.version}/{self.sha}/{self.triplet}"


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol defining the interface for storage backends.

    All storage backends must implement this protocol to be compatible
    with vcpkg-harbor. Backends are discovered via entry points.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the storage backend.

        This method is called during application startup to establish
        connections, create buckets/containers, etc.
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the storage backend and release resources."""
        ...

    @abstractmethod
    async def exists(self, name: str, version: str, sha: str, triplet: str) -> bool:
        """Check if a package exists in storage.

        Args:
            name: Package name
            version: Package version
            sha: Package SHA hash
            triplet: Target triplet (e.g., x64-linux, x64-windows)

        Returns:
            True if package exists, False otherwise
        """
        ...

    @abstractmethod
    def get(self, name: str, version: str, sha: str, triplet: str) -> AsyncIterator[bytes]:
        """Get a package from storage as an async iterator.

        Args:
            name: Package name
            version: Package version
            sha: Package SHA hash
            triplet: Target triplet (e.g., x64-linux, x64-windows)

        Yields:
            Chunks of package data

        Raises:
            PackageNotFoundError: If the package doesn't exist
        """
        ...

    @abstractmethod
    async def put(
        self,
        name: str,
        version: str,
        sha: str,
        triplet: str,
        data: AsyncIterator[bytes],
        size: int | None = None,
    ) -> PackageInfo:
        """Store a package in storage.

        Args:
            name: Package name
            version: Package version
            sha: Package SHA hash
            triplet: Target triplet (e.g., x64-linux, x64-windows)
            data: Async iterator of package data chunks
            size: Optional total size of the package

        Returns:
            PackageInfo with details about the stored package

        Raises:
            PackageAlreadyExistsError: If the package already exists
            StorageError: If the upload fails
        """
        ...

    @abstractmethod
    async def delete(self, name: str, version: str, sha: str, triplet: str) -> bool:
        """Delete a package from storage.

        Args:
            name: Package name
            version: Package version
            sha: Package SHA hash
            triplet: Target triplet (e.g., x64-linux, x64-windows)

        Returns:
            True if package was deleted, False if it didn't exist
        """
        ...

    @abstractmethod
    async def stat(self, name: str, version: str, sha: str, triplet: str) -> PackageInfo:
        """Get information about a package without downloading it.

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
        ...

    @abstractmethod
    async def list_packages(
        self,
        prefix: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[PackageInfo]:
        """List packages in storage.

        Args:
            prefix: Optional prefix to filter packages (e.g., "zlib/")
            limit: Maximum number of packages to return
            offset: Number of packages to skip

        Returns:
            List of PackageInfo objects
        """
        ...

    @abstractmethod
    async def get_stats(self) -> dict:
        """Get storage statistics.

        Returns:
            Dictionary with storage statistics (total size, count, etc.)
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the storage backend is healthy.

        Returns:
            True if healthy, False otherwise
        """
        ...
