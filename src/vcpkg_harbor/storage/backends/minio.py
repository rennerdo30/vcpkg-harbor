"""MinIO storage backend implementation."""

import asyncio
from datetime import datetime
from io import BytesIO
from typing import Any, AsyncIterator

import structlog
from minio import Minio
from minio.error import S3Error

from vcpkg_harbor.core.exceptions import (
    PackageAlreadyExistsError,
    PackageNotFoundError,
    StorageConnectionError,
    StorageError,
)
from vcpkg_harbor.storage.base import PackageInfo

logger = structlog.get_logger(__name__)


class MinioBackend:
    """MinIO/S3-compatible storage backend."""

    def __init__(
        self,
        endpoint: str = "localhost:9000",
        access_key: str = "minioadmin",
        secret_key: str = "minioadmin",
        bucket: str = "vcpkg-harbor",
        secure: bool = False,
        region: str | None = None,
    ) -> None:
        """Initialize MinIO backend.

        Args:
            endpoint: MinIO server endpoint
            access_key: Access key for authentication
            secret_key: Secret key for authentication
            bucket: Bucket name for storing packages
            secure: Use HTTPS if True
            region: Optional region for the bucket
        """
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self.secure = secure
        self.region = region
        self._client: Minio | None = None

    @property
    def client(self) -> Minio:
        """Get the MinIO client, creating it if necessary."""
        if self._client is None:
            self._client = Minio(
                self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure,
                region=self.region,
            )
        return self._client

    def _get_object_path(self, name: str, version: str, sha: str, triplet: str) -> str:
        """Generate object path from package details."""
        return f"{name}/{version}/{sha}/{triplet}"

    async def initialize(self) -> None:
        """Initialize the MinIO backend and ensure bucket exists."""
        logger.info("Initializing MinIO backend", endpoint=self.endpoint, bucket=self.bucket)

        try:
            # Run synchronous MinIO operations in thread pool
            loop = asyncio.get_event_loop()
            bucket_exists = await loop.run_in_executor(
                None, self.client.bucket_exists, self.bucket
            )

            if not bucket_exists:
                await loop.run_in_executor(None, self.client.make_bucket, self.bucket)
                logger.info("Created bucket", bucket=self.bucket)
            else:
                logger.debug("Bucket already exists", bucket=self.bucket)

        except Exception as e:
            logger.error("Failed to initialize MinIO", error=str(e))
            raise StorageConnectionError(f"Failed to connect to MinIO: {e}", cause=e)

    async def close(self) -> None:
        """Close the MinIO backend."""
        logger.debug("Closing MinIO backend")
        self._client = None

    async def exists(self, name: str, version: str, sha: str, triplet: str) -> bool:
        """Check if a package exists."""
        object_path = self._get_object_path(name, version, sha, triplet)

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, self.client.stat_object, self.bucket, object_path
            )
            return True
        except S3Error as e:
            if e.code == "NoSuchKey":
                return False
            raise StorageError(f"Error checking package existence: {e}", cause=e)

    async def get(self, name: str, version: str, sha: str, triplet: str) -> AsyncIterator[bytes]:
        """Get a package as an async iterator of bytes."""
        object_path = self._get_object_path(name, version, sha, triplet)
        logger.debug("Getting package", path=object_path)

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, self.client.get_object, self.bucket, object_path
            )

            try:
                # Read in chunks
                chunk_size = 64 * 1024  # 64KB chunks
                while True:
                    chunk = await loop.run_in_executor(None, response.read, chunk_size)
                    if not chunk:
                        break
                    yield chunk
            finally:
                response.close()
                response.release_conn()

        except S3Error as e:
            if e.code == "NoSuchKey":
                logger.warning("Package not found", path=object_path)
                raise PackageNotFoundError(name, version, sha, triplet)
            logger.error("Error getting package", path=object_path, error=str(e))
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
        object_path = self._get_object_path(name, version, sha, triplet)
        logger.debug("Putting package", path=object_path)

        # Check if already exists
        if await self.exists(name, version, sha, triplet):
            logger.warning("Package already exists", path=object_path)
            raise PackageAlreadyExistsError(name, version, sha, triplet)

        try:
            # Collect all data chunks
            chunks = []
            async for chunk in data:
                chunks.append(chunk)
            body = b"".join(chunks)
            actual_size = len(body)

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.client.put_object(
                    bucket_name=self.bucket,
                    object_name=object_path,
                    data=BytesIO(body),
                    length=actual_size,
                    content_type="application/octet-stream",
                ),
            )

            logger.info("Package uploaded", path=object_path, size=actual_size)

            return PackageInfo(
                name=name,
                version=version,
                sha=sha,
                triplet=triplet,
                size=actual_size,
                etag=result.etag if hasattr(result, "etag") else None,
                created_at=datetime.utcnow(),
            )

        except PackageAlreadyExistsError:
            raise
        except Exception as e:
            logger.error("Error uploading package", path=object_path, error=str(e))
            raise StorageError(f"Error uploading package: {e}", cause=e)

    async def delete(self, name: str, version: str, sha: str, triplet: str) -> bool:
        """Delete a package."""
        object_path = self._get_object_path(name, version, sha, triplet)
        logger.debug("Deleting package", path=object_path)

        if not await self.exists(name, version, sha, triplet):
            return False

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, self.client.remove_object, self.bucket, object_path
            )
            logger.info("Package deleted", path=object_path)
            return True
        except Exception as e:
            logger.error("Error deleting package", path=object_path, error=str(e))
            raise StorageError(f"Error deleting package: {e}", cause=e)

    async def stat(self, name: str, version: str, sha: str, triplet: str) -> PackageInfo:
        """Get package information."""
        object_path = self._get_object_path(name, version, sha, triplet)

        try:
            loop = asyncio.get_event_loop()
            stat = await loop.run_in_executor(
                None, self.client.stat_object, self.bucket, object_path
            )

            return PackageInfo(
                name=name,
                version=version,
                sha=sha,
                triplet=triplet,
                size=stat.size or 0,
                etag=stat.etag,
                content_type=stat.content_type or "application/octet-stream",
                created_at=stat.last_modified,
            )

        except S3Error as e:
            if e.code == "NoSuchKey":
                raise PackageNotFoundError(name, version, sha, triplet)
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
            objects = await loop.run_in_executor(
                None,
                lambda: list(self.client.list_objects(self.bucket, prefix=prefix, recursive=True)),
            )

            packages: list[PackageInfo] = []
            for i, obj in enumerate(objects):
                if i < offset:
                    continue
                if limit and len(packages) >= limit:
                    break

                # Parse object path (name/version/sha/triplet)
                parts = obj.object_name.split("/")
                if len(parts) >= 4:
                    packages.append(
                        PackageInfo(
                            name=parts[0],
                            version=parts[1],
                            sha=parts[2],
                            triplet=parts[3],
                            size=obj.size,
                            etag=obj.etag,
                            created_at=obj.last_modified,
                        )
                    )

            return packages

        except Exception as e:
            logger.error("Error listing packages", error=str(e))
            raise StorageError(f"Error listing packages: {e}", cause=e)

    async def get_stats(self) -> dict[str, Any]:
        """Get storage statistics."""
        try:
            packages = await self.list_packages()
            total_size = sum(p.size for p in packages)

            # Group by package name
            package_names = set(p.name for p in packages)

            return {
                "total_packages": len(packages),
                "total_size_bytes": total_size,
                "unique_package_names": len(package_names),
                "backend": "minio",
                "bucket": self.bucket,
                "endpoint": self.endpoint,
            }
        except Exception as e:
            logger.error("Error getting stats", error=str(e))
            return {
                "error": str(e),
                "backend": "minio",
            }

    async def health_check(self) -> bool:
        """Check if MinIO is healthy."""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.client.bucket_exists, self.bucket)
            return True
        except Exception as e:
            logger.warning("Health check failed", error=str(e))
            return False
