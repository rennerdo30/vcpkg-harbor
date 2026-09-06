"""Cache service for handling package operations."""

import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from vcpkg_harbor.core.exceptions import (
    PackageAlreadyExistsError,
    PackageContentConflictError,
    PackageNotFoundError,
    StorageError,
)
from vcpkg_harbor.services.tag_service import TagService
from vcpkg_harbor.storage.base import PackageInfo
from vcpkg_harbor.storage.layout import PackageKey

if TYPE_CHECKING:
    from vcpkg_harbor.core.config import Settings
    from vcpkg_harbor.storage.base import StorageBackend

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class StoredPackage:
    """Result of storing a package."""

    info: PackageInfo
    namespace: str
    tag: str | None = None
    deduplicated: bool = False
    evicted: int = 0


class CacheService:
    """Service for managing the package cache.

    Every operation takes an optional build tag. ``None`` addresses the default
    (untagged) namespace and behaves exactly as harbor did before build tags
    existed, including the storage layout.
    """

    def __init__(
        self,
        storage: "StorageBackend",
        settings: "Settings",
        tag_service: TagService | None = None,
    ) -> None:
        """Initialize the cache service.

        Args:
            storage: Storage backend instance
            settings: Application settings
            tag_service: Optional tag service, created from settings if omitted
        """
        self.storage = storage
        self.settings = settings
        self.tags = tag_service or TagService(storage, settings)
        self._read_only = settings.server.read_only
        self._write_only = settings.server.write_only

    async def check_exists(
        self,
        name: str,
        version: str,
        sha: str,
        triplet: str,
        tag: str | None = None,
    ) -> bool:
        """Check if a package exists in the cache.

        Args:
            name: Package name
            version: Package version
            sha: Package SHA hash
            triplet: Target triplet (e.g., x64-linux, x64-windows)
            tag: Optional build tag

        Returns:
            True if the package exists in the addressed namespace
        """
        key = PackageKey(name, version, sha, triplet)
        namespace = self.tags.resolve_namespace(tag)

        logger.debug("Checking package existence", package=key.path, namespace=namespace)

        try:
            visible, scope = await self.tags.resolve_read(namespace, key)
            exists = visible and await self.storage.exists(name, version, sha, triplet, scope=scope)
            if exists:
                logger.info("Package exists", package=key.path, namespace=namespace)
            else:
                logger.info("Package not found", package=key.path, namespace=namespace)
            return exists
        except Exception as e:
            logger.error(
                "Error checking package existence",
                package=key.path,
                namespace=namespace,
                error=str(e),
            )
            raise StorageError(f"Error checking package existence: {e}", cause=e)

    async def get_package(
        self,
        name: str,
        version: str,
        sha: str,
        triplet: str,
        tag: str | None = None,
    ) -> AsyncIterator[bytes]:
        """Get a package from the cache.

        Args:
            name: Package name
            version: Package version
            sha: Package SHA hash
            triplet: Target triplet (e.g., x64-linux, x64-windows)
            tag: Optional build tag

        Yields:
            Package data chunks

        Raises:
            PackageNotFoundError: If the package doesn't exist in the namespace
            StorageError: If there's an error retrieving the package
        """
        key = PackageKey(name, version, sha, triplet)
        namespace = self.tags.resolve_namespace(tag)

        if self._write_only:
            logger.warning(
                "Read operation blocked in write-only mode",
                package=key.path,
                namespace=namespace,
            )
            raise PackageNotFoundError(name, version, sha, triplet)

        visible, scope = await self.tags.resolve_read(namespace, key)
        if not visible:
            logger.warning("Package not in namespace", package=key.path, namespace=namespace)
            raise PackageNotFoundError(name, version, sha, triplet)

        logger.info("Downloading package", package=key.path, namespace=namespace)

        try:
            async for chunk in self.storage.get(name, version, sha, triplet, scope=scope):
                yield chunk
            logger.info("Package download complete", package=key.path, namespace=namespace)
        except PackageNotFoundError:
            logger.warning("Package not found", package=key.path, namespace=namespace)
            raise
        except Exception as e:
            logger.error(
                "Error downloading package",
                package=key.path,
                namespace=namespace,
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
        tag: str | None = None,
    ) -> "StoredPackage":
        """Store a package in the cache.

        With deduplication enabled the bytes are stored once per package
        identity, after verifying that the uploaded bytes match the stored bytes.
        Different content for an existing identity is rejected without adding a
        reference to the requesting namespace.

        Args:
            name: Package name
            version: Package version
            sha: Package SHA hash
            triplet: Target triplet (e.g., x64-linux, x64-windows)
            data: Async iterator of package data
            size: Optional total size of the package
            tag: Optional build tag

        Returns:
            StoredPackage describing what was stored

        Raises:
            PackageAlreadyExistsError: If the namespace already holds the package
            StorageError: If there's an error storing the package
        """
        async with self.tags.mutation_lock:
            key = PackageKey(name, version, sha, triplet)
            namespace = self.tags.resolve_namespace(tag)

            if self._read_only:
                logger.warning(
                    "Write operation blocked in read-only mode",
                    package=key.path,
                    namespace=namespace,
                )
                raise StorageError("Server is in read-only mode")

            logger.info("Uploading package", package=key.path, namespace=namespace, size=size)

            if not self.tags.enabled:
                # Build tags disabled: behave exactly like the untagged flat layout.
                info = await self._store_bytes(key, data, size, scope=None)
                return StoredPackage(info=info, namespace=namespace, tag=tag)

            # A package stored before the index existed is claimed by the default
            # namespace first, so tagging it never hides it from untagged clients.
            await self.tags.adopt_legacy(key)

            visible, existing_scope = await self.tags.resolve_read(namespace, key)
            if visible and await self.storage.exists(
                name, version, sha, triplet, scope=existing_scope
            ):
                logger.warning("Package already exists", package=key.path, namespace=namespace)
                raise PackageAlreadyExistsError(name, version, sha, triplet)

            scope = self.tags.object_scope(namespace)
            deduplicated = await self.storage.exists(name, version, sha, triplet, scope=scope)

            if deduplicated:
                incoming_digest = await self._digest(data)
                stored_digest = await self._digest(
                    self.storage.get(name, version, sha, triplet, scope=scope)
                )
                if incoming_digest != stored_digest:
                    raise PackageContentConflictError(
                        "Package identity already contains different bytes; use a new ABI hash "
                        "or disable cross-tag deduplication"
                    )
                info = await self.storage.stat(name, version, sha, triplet, scope=scope)
                logger.info(
                    "Package deduplicated, added a reference instead of storing bytes",
                    package=key.path,
                    namespace=namespace,
                    size=info.size,
                )
            else:
                info = await self._store_bytes(key, data, size, scope=scope)

            info.tag = tag
            await self.tags.register(namespace, key, info.size, scope=scope)
            evicted = await self.tags.enforce_retention(namespace, keep=key)

            return StoredPackage(
                info=info,
                namespace=namespace,
                tag=tag,
                deduplicated=deduplicated,
                evicted=len(evicted),
            )

    async def _store_bytes(
        self,
        key: PackageKey,
        data: AsyncIterator[bytes],
        size: int | None,
        scope: str | None,
    ) -> PackageInfo:
        """Write package bytes to storage, translating backend failures."""
        try:
            info = await self.storage.put(
                key.name, key.version, key.sha, key.triplet, data, size, scope=scope
            )
            logger.info("Package uploaded successfully", package=key.path, size=info.size)
            return info
        except PackageAlreadyExistsError:
            logger.warning("Package already exists", package=key.path)
            raise
        except Exception as e:
            logger.error("Error uploading package", package=key.path, error=str(e))
            raise StorageError(f"Error uploading package: {e}", cause=e)

    @staticmethod
    async def _digest(data: AsyncIterator[bytes]) -> bytes:
        """Hash a stream without buffering the package in memory."""
        digest = hashlib.sha256()
        async for chunk in data:
            digest.update(chunk)
        return digest.digest()

    async def delete_package(
        self,
        name: str,
        version: str,
        sha: str,
        triplet: str,
        tag: str | None = None,
    ) -> bool:
        """Delete a package from the cache.

        Only the addressed namespace's reference is dropped. The bytes survive
        as long as another namespace still references them.

        Args:
            name: Package name
            version: Package version
            sha: Package SHA hash
            triplet: Target triplet (e.g., x64-linux, x64-windows)
            tag: Optional build tag

        Returns:
            True if the package was removed from the namespace, False if the
            namespace did not hold it

        Raises:
            StorageError: If there's an error deleting the package
        """
        async with self.tags.mutation_lock:
            key = PackageKey(name, version, sha, triplet)
            namespace = self.tags.resolve_namespace(tag)

            if self._read_only:
                logger.warning(
                    "Delete operation blocked in read-only mode",
                    package=key.path,
                    namespace=namespace,
                )
                raise StorageError("Server is in read-only mode")

            logger.info("Deleting package", package=key.path, namespace=namespace)

            try:
                visible, scope = await self.tags.resolve_read(namespace, key)
                if not visible:
                    logger.info(
                        "Package not found for deletion", package=key.path, namespace=namespace
                    )
                    return False

                if self.tags.enabled:
                    remaining = await self.tags.unregister(namespace, key)
                    if not self.tags.should_delete_object(scope, remaining):
                        logger.info(
                            "Package still referenced by other namespaces, bytes kept",
                            package=key.path,
                            namespace=namespace,
                            references=remaining,
                        )
                        return True

                deleted = await self.storage.delete(name, version, sha, triplet, scope=scope)
                if deleted:
                    logger.info("Package deleted", package=key.path, namespace=namespace)
                else:
                    logger.info(
                        "Package not found for deletion", package=key.path, namespace=namespace
                    )
                return deleted or (self.tags.enabled and visible)
            except Exception as e:
                logger.error(
                    "Error deleting package",
                    package=key.path,
                    namespace=namespace,
                    error=str(e),
                )
                raise StorageError(f"Error deleting package: {e}", cause=e)

    async def get_package_info(
        self,
        name: str,
        version: str,
        sha: str,
        triplet: str,
        tag: str | None = None,
    ) -> PackageInfo:
        """Get package information without downloading.

        Args:
            name: Package name
            version: Package version
            sha: Package SHA hash
            triplet: Target triplet (e.g., x64-linux, x64-windows)
            tag: Optional build tag

        Returns:
            PackageInfo with package metadata

        Raises:
            PackageNotFoundError: If the package doesn't exist in the namespace
        """
        key = PackageKey(name, version, sha, triplet)
        namespace = self.tags.resolve_namespace(tag)

        visible, scope = await self.tags.resolve_read(namespace, key)
        if not visible:
            raise PackageNotFoundError(name, version, sha, triplet)

        info = await self.storage.stat(name, version, sha, triplet, scope=scope)
        info.tag = tag
        return info
