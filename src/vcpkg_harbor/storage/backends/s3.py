"""AWS S3 storage backend implementation."""

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from io import BytesIO
from typing import Any

import structlog

from vcpkg_harbor.core.exceptions import (
    PackageAlreadyExistsError,
    PackageNotFoundError,
    StorageConnectionError,
    StorageError,
)
from vcpkg_harbor.storage.base import PackageInfo
from vcpkg_harbor.storage.layout import object_key, parse_object_key

logger = structlog.get_logger(__name__)


class S3Backend:
    """AWS S3 storage backend."""

    def __init__(
        self,
        bucket: str = "vcpkg-harbor",
        region: str = "us-east-1",
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        endpoint_url: str | None = None,
    ) -> None:
        """Initialize S3 backend.

        Args:
            bucket: S3 bucket name
            region: AWS region
            access_key_id: AWS access key ID (uses default credentials if not provided)
            secret_access_key: AWS secret access key
            endpoint_url: Custom S3 endpoint URL (for S3-compatible services)
        """
        self.bucket = bucket
        self.region = region
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.endpoint_url = endpoint_url
        self._client = None

    @property
    def client(self) -> Any:
        """Get the boto3 S3 client."""
        if self._client is None:
            import boto3

            kwargs = {"region_name": self.region}

            if self.access_key_id and self.secret_access_key:
                kwargs["aws_access_key_id"] = self.access_key_id
                kwargs["aws_secret_access_key"] = self.secret_access_key

            if self.endpoint_url:
                kwargs["endpoint_url"] = self.endpoint_url

            self._client = boto3.client("s3", **kwargs)

        return self._client

    def _get_object_key(
        self,
        name: str,
        version: str,
        sha: str,
        triplet: str,
        scope: str | None = None,
    ) -> str:
        """Generate S3 object key from package details."""
        return object_key(name, version, sha, triplet, scope)

    async def initialize(self) -> None:
        """Initialize the S3 backend and ensure bucket exists."""
        logger.info("Initializing S3 backend", bucket=self.bucket, region=self.region)

        try:
            loop = asyncio.get_event_loop()

            # Check if bucket exists
            try:
                await loop.run_in_executor(None, self.client.head_bucket, {"Bucket": self.bucket})
                logger.debug("Bucket exists", bucket=self.bucket)
            except Exception:
                # Create bucket
                await loop.run_in_executor(
                    None,
                    lambda: self.client.create_bucket(
                        Bucket=self.bucket,
                        CreateBucketConfiguration={"LocationConstraint": self.region}
                        if self.region != "us-east-1"
                        else {},
                    ),
                )
                logger.info("Created bucket", bucket=self.bucket)

        except Exception as e:
            logger.error("Failed to initialize S3", error=str(e))
            raise StorageConnectionError(f"Failed to initialize S3: {e}", cause=e)

    async def close(self) -> None:
        """Close the S3 backend."""
        logger.debug("Closing S3 backend")
        self._client = None

    async def exists(
        self,
        name: str,
        version: str,
        sha: str,
        triplet: str,
        scope: str | None = None,
    ) -> bool:
        """Check if a package exists."""
        key = self._get_object_key(name, version, sha, triplet, scope)

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.head_object(Bucket=self.bucket, Key=key),
            )
            return True
        except Exception as e:
            if "404" in str(e) or "NoSuchKey" in str(e):
                return False
            raise StorageError(f"Error checking package existence: {e}", cause=e)

    async def get(
        self,
        name: str,
        version: str,
        sha: str,
        triplet: str,
        scope: str | None = None,
    ) -> AsyncIterator[bytes]:
        """Get a package as an async iterator of bytes."""
        key = self._get_object_key(name, version, sha, triplet, scope)
        logger.debug("Getting package", key=key)

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.get_object(Bucket=self.bucket, Key=key),
            )

            body = response["Body"]
            chunk_size = 64 * 1024

            try:
                while True:
                    chunk = await loop.run_in_executor(None, body.read, chunk_size)
                    if not chunk:
                        break
                    yield chunk
            finally:
                body.close()

        except Exception as e:
            if "NoSuchKey" in str(e) or "404" in str(e):
                logger.warning("Package not found", key=key)
                raise PackageNotFoundError(name, version, sha, triplet)
            logger.error("Error getting package", key=key, error=str(e))
            raise StorageError(f"Error getting package: {e}", cause=e)

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
        """Store a package."""
        key = self._get_object_key(name, version, sha, triplet, scope)
        logger.debug("Putting package", key=key)

        if await self.exists(name, version, sha, triplet, scope):
            logger.warning("Package already exists", key=key)
            raise PackageAlreadyExistsError(name, version, sha, triplet)

        try:
            chunks = []
            async for chunk in data:
                chunks.append(chunk)
            body = b"".join(chunks)
            actual_size = len(body)

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self.client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=BytesIO(body),
                    ContentType="application/octet-stream",
                ),
            )

            logger.info("Package uploaded", key=key, size=actual_size)

            return PackageInfo(
                name=name,
                version=version,
                sha=sha,
                triplet=triplet,
                size=actual_size,
                etag=result.get("ETag", "").strip('"'),
                created_at=datetime.utcnow(),
            )

        except PackageAlreadyExistsError:
            raise
        except Exception as e:
            logger.error("Error uploading package", key=key, error=str(e))
            raise StorageError(f"Error uploading package: {e}", cause=e)

    async def delete(
        self,
        name: str,
        version: str,
        sha: str,
        triplet: str,
        scope: str | None = None,
    ) -> bool:
        """Delete a package."""
        key = self._get_object_key(name, version, sha, triplet, scope)
        logger.debug("Deleting package", key=key)

        if not await self.exists(name, version, sha, triplet, scope):
            return False

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.delete_object(Bucket=self.bucket, Key=key),
            )
            logger.info("Package deleted", key=key)
            return True
        except Exception as e:
            logger.error("Error deleting package", key=key, error=str(e))
            raise StorageError(f"Error deleting package: {e}", cause=e)

    async def stat(
        self,
        name: str,
        version: str,
        sha: str,
        triplet: str,
        scope: str | None = None,
    ) -> PackageInfo:
        """Get package information."""
        key = self._get_object_key(name, version, sha, triplet, scope)

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.head_object(Bucket=self.bucket, Key=key),
            )

            return PackageInfo(
                name=name,
                version=version,
                sha=sha,
                triplet=triplet,
                size=response["ContentLength"],
                etag=response.get("ETag", "").strip('"'),
                content_type=response.get("ContentType", "application/octet-stream"),
                created_at=response.get("LastModified"),
            )

        except Exception as e:
            if "404" in str(e) or "NoSuchKey" in str(e):
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
            paginator = self.client.get_paginator("list_objects_v2")

            kwargs = {"Bucket": self.bucket}
            if prefix:
                kwargs["Prefix"] = prefix

            packages = []
            count = 0

            for page in paginator.paginate(**kwargs):
                for obj in page.get("Contents", []):
                    parsed = parse_object_key(obj["Key"])
                    if parsed is None:
                        # Bookkeeping documents are not packages.
                        continue

                    count += 1
                    if count <= offset:
                        continue

                    packages.append(
                        PackageInfo(
                            name=parsed.key.name,
                            version=parsed.key.version,
                            sha=parsed.key.sha,
                            triplet=parsed.key.triplet,
                            size=obj["Size"],
                            etag=obj.get("ETag", "").strip('"'),
                            created_at=obj.get("LastModified"),
                            tag=parsed.tag,
                        )
                    )

                    if limit and len(packages) >= limit:
                        return packages

            return packages

        except Exception as e:
            logger.error("Error listing packages", error=str(e))
            raise StorageError(f"Error listing packages: {e}", cause=e)

    async def put_metadata(self, key: str, data: bytes) -> None:
        """Store a bookkeeping document."""
        logger.debug("Writing metadata", key=key, size=len(data))

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=BytesIO(data),
                    ContentType="application/json",
                ),
            )
        except Exception as e:
            logger.error("Error writing metadata", key=key, error=str(e))
            raise StorageError(f"Error writing metadata: {e}", cause=e)

    async def get_metadata(self, key: str) -> bytes | None:
        """Read a bookkeeping document."""
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.get_object(Bucket=self.bucket, Key=key),
            )
            body = response["Body"]
            try:
                return bytes(await loop.run_in_executor(None, body.read))
            finally:
                body.close()
        except Exception as e:
            if "NoSuchKey" in str(e) or "404" in str(e):
                return None
            logger.error("Error reading metadata", key=key, error=str(e))
            raise StorageError(f"Error reading metadata: {e}", cause=e)

    async def delete_metadata(self, key: str) -> bool:
        """Delete a bookkeeping document."""
        loop = asyncio.get_event_loop()

        try:
            await loop.run_in_executor(
                None,
                lambda: self.client.head_object(Bucket=self.bucket, Key=key),
            )
        except Exception as e:
            if "404" in str(e) or "NoSuchKey" in str(e):
                return False
            raise StorageError(f"Error deleting metadata: {e}", cause=e)

        try:
            await loop.run_in_executor(
                None,
                lambda: self.client.delete_object(Bucket=self.bucket, Key=key),
            )
            return True
        except Exception as e:
            logger.error("Error deleting metadata", key=key, error=str(e))
            raise StorageError(f"Error deleting metadata: {e}", cause=e)

    async def list_metadata(self, prefix: str) -> list[str]:
        """List bookkeeping document keys under a prefix."""
        try:
            loop = asyncio.get_event_loop()

            def _list() -> list[str]:
                paginator = self.client.get_paginator("list_objects_v2")
                keys: list[str] = []
                for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                    keys.extend(obj["Key"] for obj in page.get("Contents", []))
                return keys

            return sorted(await loop.run_in_executor(None, _list))
        except Exception as e:
            logger.error("Error listing metadata", prefix=prefix, error=str(e))
            raise StorageError(f"Error listing metadata: {e}", cause=e)

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
                "backend": "s3",
                "bucket": self.bucket,
                "region": self.region,
            }
        except Exception as e:
            logger.error("Error getting stats", error=str(e))
            return {"error": str(e), "backend": "s3"}

    async def health_check(self) -> bool:
        """Check if S3 is healthy."""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.client.head_bucket(Bucket=self.bucket),
            )
            return True
        except Exception as e:
            logger.warning("Health check failed", error=str(e))
            return False
