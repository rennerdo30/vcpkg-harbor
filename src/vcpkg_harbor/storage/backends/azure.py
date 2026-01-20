"""Azure Blob Storage backend implementation."""

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, cast

import structlog

from vcpkg_harbor.core.exceptions import (
    PackageAlreadyExistsError,
    PackageNotFoundError,
    StorageConnectionError,
    StorageError,
)
from vcpkg_harbor.storage.base import PackageInfo

logger = structlog.get_logger(__name__)


class AzureBackend:
    """Azure Blob Storage backend."""

    def __init__(
        self,
        connection_string: str | None = None,
        account_name: str | None = None,
        account_key: str | None = None,
        container: str = "vcpkg-harbor",
    ) -> None:
        """Initialize Azure backend.

        Args:
            connection_string: Azure connection string (preferred)
            account_name: Azure storage account name
            account_key: Azure storage account key
            container: Container name for storing packages
        """
        self.connection_string = connection_string
        self.account_name = account_name
        self.account_key = account_key
        self.container = container
        self._client: Any = None
        self._container_client = None

    @property
    def container_client(self) -> Any:
        """Get the Azure container client."""
        if self._container_client is None:
            from azure.storage.blob import BlobServiceClient

            if self.connection_string:
                self._client = BlobServiceClient.from_connection_string(self.connection_string)
            elif self.account_name and self.account_key:
                account_url = f"https://{self.account_name}.blob.core.windows.net"
                self._client = BlobServiceClient(
                    account_url=account_url, credential=self.account_key
                )
            else:
                raise StorageConnectionError(
                    "Azure storage requires either connection_string or account_name/account_key"
                )

            self._container_client = cast(Any, self._client).get_container_client(self.container)

        return self._container_client

    def _get_blob_name(self, name: str, version: str, sha: str, triplet: str) -> str:
        """Generate blob name from package details."""
        return f"{name}/{version}/{sha}/{triplet}"

    async def initialize(self) -> None:
        """Initialize the Azure backend and ensure container exists."""
        logger.info("Initializing Azure backend", container=self.container)

        try:
            loop = asyncio.get_event_loop()

            exists = await loop.run_in_executor(None, self.container_client.exists)
            if not exists:
                await loop.run_in_executor(None, self.container_client.create_container)
                logger.info("Created container", container=self.container)
            else:
                logger.debug("Container exists", container=self.container)

        except Exception as e:
            logger.error("Failed to initialize Azure", error=str(e))
            raise StorageConnectionError(f"Failed to initialize Azure: {e}", cause=e)

    async def close(self) -> None:
        """Close the Azure backend."""
        logger.debug("Closing Azure backend")
        if self._client:
            self._client.close()
        self._client = None
        self._container_client = None

    async def exists(self, name: str, version: str, sha: str, triplet: str) -> bool:
        """Check if a package exists."""
        blob_name = self._get_blob_name(name, version, sha, triplet)

        try:
            loop = asyncio.get_event_loop()
            blob_client = self.container_client.get_blob_client(blob_name)
            return await loop.run_in_executor(None, blob_client.exists)
        except Exception as e:
            raise StorageError(f"Error checking package existence: {e}", cause=e)

    async def get(self, name: str, version: str, sha: str, triplet: str) -> AsyncIterator[bytes]:
        """Get a package as an async iterator of bytes."""
        blob_name = self._get_blob_name(name, version, sha, triplet)
        logger.debug("Getting package", blob=blob_name)

        if not await self.exists(name, version, sha, triplet):
            logger.warning("Package not found", blob=blob_name)
            raise PackageNotFoundError(name, version, sha, triplet)

        try:
            loop = asyncio.get_event_loop()
            blob_client = self.container_client.get_blob_client(blob_name)
            downloader = await loop.run_in_executor(None, blob_client.download_blob)

            for chunk in downloader.chunks():
                yield chunk

        except PackageNotFoundError:
            raise
        except Exception as e:
            logger.error("Error getting package", blob=blob_name, error=str(e))
            raise StorageError(f"Error getting package: {e}", cause=e)

    async def put(
        self,
        name: str,
        version: str,
        sha: str,
        triplet: str,
        data: AsyncIterator[bytes],
        size: int | None = None,
    ) -> PackageInfo:
        """Store a package."""
        blob_name = self._get_blob_name(name, version, sha, triplet)
        logger.debug("Putting package", blob=blob_name)

        if await self.exists(name, version, sha, triplet):
            logger.warning("Package already exists", blob=blob_name)
            raise PackageAlreadyExistsError(name, version, sha, triplet)

        try:
            chunks = []
            async for chunk in data:
                chunks.append(chunk)
            body = b"".join(chunks)
            actual_size = len(body)

            loop = asyncio.get_event_loop()
            blob_client = self.container_client.get_blob_client(blob_name)
            result = await loop.run_in_executor(
                None,
                lambda: blob_client.upload_blob(body, content_type="application/octet-stream"),
            )

            logger.info("Package uploaded", blob=blob_name, size=actual_size)

            return PackageInfo(
                name=name,
                version=version,
                sha=sha,
                triplet=triplet,
                size=actual_size,
                etag=result.get("etag", "").strip('"'),
                created_at=datetime.utcnow(),
            )

        except PackageAlreadyExistsError:
            raise
        except Exception as e:
            logger.error("Error uploading package", blob=blob_name, error=str(e))
            raise StorageError(f"Error uploading package: {e}", cause=e)

    async def delete(self, name: str, version: str, sha: str, triplet: str) -> bool:
        """Delete a package."""
        blob_name = self._get_blob_name(name, version, sha, triplet)
        logger.debug("Deleting package", blob=blob_name)

        if not await self.exists(name, version, sha, triplet):
            return False

        try:
            loop = asyncio.get_event_loop()
            blob_client = self.container_client.get_blob_client(blob_name)
            await loop.run_in_executor(None, blob_client.delete_blob)
            logger.info("Package deleted", blob=blob_name)
            return True
        except Exception as e:
            logger.error("Error deleting package", blob=blob_name, error=str(e))
            raise StorageError(f"Error deleting package: {e}", cause=e)

    async def stat(self, name: str, version: str, sha: str, triplet: str) -> PackageInfo:
        """Get package information."""
        blob_name = self._get_blob_name(name, version, sha, triplet)

        if not await self.exists(name, version, sha, triplet):
            raise PackageNotFoundError(name, version, sha, triplet)

        try:
            loop = asyncio.get_event_loop()
            blob_client = self.container_client.get_blob_client(blob_name)
            properties = await loop.run_in_executor(None, blob_client.get_blob_properties)

            return PackageInfo(
                name=name,
                version=version,
                sha=sha,
                triplet=triplet,
                size=properties.size,
                etag=properties.etag.strip('"') if properties.etag else None,
                content_type=properties.content_settings.content_type or "application/octet-stream",
                created_at=properties.creation_time,
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

        try:
            loop = asyncio.get_event_loop()
            blobs = await loop.run_in_executor(
                None,
                lambda: list(self.container_client.list_blobs(name_starts_with=prefix)),
            )

            packages = []
            for i, blob in enumerate(blobs):
                if i < offset:
                    continue

                parts = blob.name.split("/")
                if len(parts) >= 4:
                    packages.append(
                        PackageInfo(
                            name=parts[0],
                            version=parts[1],
                            sha=parts[2],
                            triplet=parts[3],
                            size=blob.size,
                            etag=blob.etag.strip('"') if blob.etag else None,
                            created_at=blob.creation_time,
                        )
                    )

                if limit and len(packages) >= limit:
                    break

            return packages

        except Exception as e:
            logger.error("Error listing packages", error=str(e))
            raise StorageError(f"Error listing packages: {e}", cause=e)

    async def get_stats(self) -> dict[str, Any]:
        """Get storage statistics."""
        try:
            packages = await self.list_packages()
            total_size = sum(p.size for p in packages)
            package_names = {p.name for p in packages}

            return {
                "total_packages": len(packages),
                "total_size_bytes": total_size,
                "unique_package_names": len(package_names),
                "backend": "azure",
                "container": self.container,
            }
        except Exception as e:
            logger.error("Error getting stats", error=str(e))
            return {"error": str(e), "backend": "azure"}

    async def health_check(self) -> bool:
        """Check if Azure is healthy."""
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self.container_client.exists)
        except Exception as e:
            logger.warning("Health check failed", error=str(e))
            return False
