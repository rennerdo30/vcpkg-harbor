"""Base storage protocol for vcpkg-harbor storage backends."""

from abc import abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from vcpkg_harbor.storage.layout import PackageKey


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
    metadata: dict[str, Any] | None = None
    tag: str | None = None

    @property
    def object_path(self) -> str:
        """Get the storage object path."""
        return f"{self.name}/{self.version}/{self.sha}/{self.triplet}"

    @property
    def key(self) -> PackageKey:
        """Get the package identity."""
        return PackageKey(self.name, self.version, self.sha, self.triplet)


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
    async def exists(
        self,
        name: str,
        version: str,
        sha: str,
        triplet: str,
        scope: str | None = None,
    ) -> bool:
        """Check if a package exists in storage.

        Args:
            name: Package name
            version: Package version
            sha: Package SHA hash
            triplet: Target triplet (e.g., x64-linux, x64-windows)
            scope: Optional key prefix. ``None`` addresses the shared identity
                key (see :mod:`vcpkg_harbor.storage.layout`).

        Returns:
            True if package exists, False otherwise
        """
        ...

    @abstractmethod
    def get(
        self,
        name: str,
        version: str,
        sha: str,
        triplet: str,
        scope: str | None = None,
    ) -> AsyncIterator[bytes]:
        """Get a package from storage as an async iterator.

        Args:
            name: Package name
            version: Package version
            sha: Package SHA hash
            triplet: Target triplet (e.g., x64-linux, x64-windows)
            scope: Optional key prefix

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
        scope: str | None = None,
    ) -> PackageInfo:
        """Store a package in storage.

        Args:
            name: Package name
            version: Package version
            sha: Package SHA hash
            triplet: Target triplet (e.g., x64-linux, x64-windows)
            data: Async iterator of package data chunks
            size: Optional total size of the package
            scope: Optional key prefix

        Returns:
            PackageInfo with details about the stored package

        Raises:
            PackageAlreadyExistsError: If the package already exists
            StorageError: If the upload fails
        """
        ...

    @abstractmethod
    async def delete(
        self,
        name: str,
        version: str,
        sha: str,
        triplet: str,
        scope: str | None = None,
    ) -> bool:
        """Delete a package from storage.

        Args:
            name: Package name
            version: Package version
            sha: Package SHA hash
            triplet: Target triplet (e.g., x64-linux, x64-windows)
            scope: Optional key prefix

        Returns:
            True if package was deleted, False if it didn't exist
        """
        ...

    @abstractmethod
    async def stat(
        self,
        name: str,
        version: str,
        sha: str,
        triplet: str,
        scope: str | None = None,
    ) -> PackageInfo:
        """Get information about a package without downloading it.

        Args:
            name: Package name
            version: Package version
            sha: Package SHA hash
            triplet: Target triplet (e.g., x64-linux, x64-windows)
            scope: Optional key prefix

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
    async def put_metadata(self, key: str, data: bytes) -> None:
        """Store a small bookkeeping document.

        Metadata objects live under the reserved ``_harbor/`` prefix and hold
        harbor's own state (the build tag index and reference counters). They
        are always small, so backends may buffer them in memory. Writes must
        overwrite an existing document rather than fail.

        Args:
            key: Full object key, always under the reserved prefix
            data: Document payload

        Raises:
            StorageError: If the write fails
        """
        ...

    @abstractmethod
    async def get_metadata(self, key: str) -> bytes | None:
        """Read a bookkeeping document.

        Args:
            key: Full object key, always under the reserved prefix

        Returns:
            The document payload, or ``None`` if it does not exist

        Raises:
            StorageError: If the read fails for any reason other than absence
        """
        ...

    @abstractmethod
    async def delete_metadata(self, key: str) -> bool:
        """Delete a bookkeeping document.

        Args:
            key: Full object key, always under the reserved prefix

        Returns:
            True if the document was deleted, False if it did not exist
        """
        ...

    @abstractmethod
    async def list_metadata(self, prefix: str) -> list[str]:
        """List bookkeeping document keys under a prefix.

        Args:
            prefix: Key prefix, always under the reserved prefix

        Returns:
            Sorted list of matching keys
        """
        ...

    @abstractmethod
    async def get_stats(self) -> dict[str, Any]:
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
