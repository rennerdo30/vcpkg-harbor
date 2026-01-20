"""Google Cloud Storage backend implementation."""

import asyncio
from datetime import datetime
from typing import AsyncIterator

import structlog

from vcpkg_harbor.core.exceptions import (
    PackageAlreadyExistsError,
    PackageNotFoundError,
    StorageConnectionError,
    StorageError,
)
from vcpkg_harbor.storage.base import PackageInfo

logger = structlog.get_logger(__name__)


class GCSBackend:
    """Google Cloud Storage backend."""

    def __init__(
        self,
        bucket: str = "vcpkg-harbor",
        project: str | None = None,
        credentials_file: str | None = None,
    ) -> None:
        """Initialize GCS backend.

        Args:
            bucket: GCS bucket name
            project: GCP project ID
            credentials_file: Path to service account JSON credentials
        """
        self.bucket_name = bucket
        self.project = project
        self.credentials_file = credentials_file
        self._client = None
        self._bucket = None

    @property
    def bucket(self):
        """Get the GCS bucket."""
        if self._bucket is None:
            from google.cloud import storage
            from google.oauth2 import service_account

            if self.credentials_file:
                credentials = service_account.Credentials.from_service_account_file(
                    self.credentials_file
                )
                self._client = storage.Client(credentials=credentials, project=self.project)
            else:
                self._client = storage.Client(project=self.project)

            self._bucket = self._client.bucket(self.bucket_name)

        return self._bucket

    def _get_blob_name(self, name: str, version: str, sha: str, triplet: str) -> str:
        """Generate blob name from package details."""
        return f"{name}/{version}/{sha}/{triplet}"

    async def initialize(self) -> None:
        """Initialize the GCS backend and ensure bucket exists."""
        logger.info("Initializing GCS backend", bucket=self.bucket_name)

        try:
            loop = asyncio.get_event_loop()

            exists = await loop.run_in_executor(None, self.bucket.exists)
            if not exists:
                await loop.run_in_executor(
                    None,
                    lambda: self._client.create_bucket(self.bucket, location="US"),
                )
                logger.info("Created bucket", bucket=self.bucket_name)
            else:
                logger.debug("Bucket exists", bucket=self.bucket_name)

        except Exception as e:
            logger.error("Failed to initialize GCS", error=str(e))
            raise StorageConnectionError(f"Failed to initialize GCS: {e}", cause=e)

    async def close(self) -> None:
        """Close the GCS backend."""
        logger.debug("Closing GCS backend")
        if self._client:
            self._client.close()
        self._client = None
        self._bucket = None

    async def exists(self, name: str, version: str, sha: str, triplet: str) -> bool:
        """Check if a package exists."""
        blob_name = self._get_blob_name(name, version, sha, triplet)

        try:
            loop = asyncio.get_event_loop()
            blob = self.bucket.blob(blob_name)
            return await loop.run_in_executor(None, blob.exists)
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
            blob = self.bucket.blob(blob_name)
            data = await loop.run_in_executor(None, blob.download_as_bytes)

            # Yield in chunks
            chunk_size = 64 * 1024
            for i in range(0, len(data), chunk_size):
                yield data[i : i + chunk_size]

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
            blob = self.bucket.blob(blob_name)
            await loop.run_in_executor(
                None,
                lambda: blob.upload_from_string(body, content_type="application/octet-stream"),
            )

            # Reload to get metadata
            await loop.run_in_executor(None, blob.reload)

            logger.info("Package uploaded", blob=blob_name, size=actual_size)

            return PackageInfo(
                name=name,
                version=version,
                sha=sha,
                triplet=triplet,
                size=actual_size,
                etag=blob.etag,
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
            blob = self.bucket.blob(blob_name)
            await loop.run_in_executor(None, blob.delete)
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
            blob = self.bucket.blob(blob_name)
            await loop.run_in_executor(None, blob.reload)

            return PackageInfo(
                name=name,
                version=version,
                sha=sha,
                triplet=triplet,
                size=blob.size or 0,
                etag=blob.etag,
                content_type=blob.content_type or "application/octet-stream",
                created_at=blob.time_created,
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
                lambda: list(self._client.list_blobs(self.bucket_name, prefix=prefix)),
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
                            size=blob.size or 0,
                            etag=blob.etag,
                            created_at=blob.time_created,
                        )
                    )

                if limit and len(packages) >= limit:
                    break

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

            return {
                "total_packages": len(packages),
                "total_size_bytes": total_size,
                "unique_package_names": len(package_names),
                "backend": "gcs",
                "bucket": self.bucket_name,
                "project": self.project,
            }
        except Exception as e:
            logger.error("Error getting stats", error=str(e))
            return {"error": str(e), "backend": "gcs"}

    async def health_check(self) -> bool:
        """Check if GCS is healthy."""
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self.bucket.exists)
        except Exception as e:
            logger.warning("Health check failed", error=str(e))
            return False
