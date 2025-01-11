import io
from datetime import datetime, timezone
from typing import BinaryIO, List, Optional
import json

import structlog
from minio import Minio
from minio.error import S3Error
from tenacity import retry, stop_after_attempt, wait_exponential

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

class MinioStorageError(StorageError):
    """MinIO-specific storage error."""
    pass

class MinioStorageBackend(BaseStorageBackend):
    """MinIO storage backend implementation."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: Optional[str] = None,
        secure: bool = True,
        connect_timeout: int = 10,
        read_timeout: int = 30,
    ):
        """Initialize MinIO storage backend.
        
        Args:
            endpoint: MinIO server endpoint
            access_key: Access key
            secret_key: Secret key
            bucket: Bucket name
            region: Optional region name
            secure: Use HTTPS if True
            connect_timeout: Connection timeout in seconds
            read_timeout: Read timeout in seconds
        """
        self.client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
            region=region,
        )
        self.bucket = bucket
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.metadata_suffix = ".meta.json"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    async def initialize(self) -> None:
        """Initialize the storage backend."""
        await super().initialize()
        try:
            # Ensure bucket exists
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
                logger.info("bucket_created", bucket=self.bucket)
            logger.info("minio_storage_initialized", bucket=self.bucket)
        except S3Error as e:
            raise MinioStorageError(f"Failed to initialize storage: {e}")

    def _get_object_name(self, package: PackageIdentifier) -> str:
        """Get the object name for a package."""
        return f"{package.name}/{package.version}/{package.sha}"

    def _get_metadata_name(self, package: PackageIdentifier) -> str:
        """Get the metadata object name for a package."""
        return f"{self._get_object_name(package)}{self.metadata_suffix}"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    async def get(self, package: PackageIdentifier, writer: BinaryIO) -> None:
        """Get a package from storage."""
        self._validate_package(package)
        object_name = self._get_object_name(package)

        try:
            response = None
            try:
                response = self.client.get_object(
                    bucket_name=self.bucket,
                    object_name=object_name,
                )
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    writer.write(chunk)
                logger.info("package_retrieved", package=str(package))
            finally:
                if response:
                    response.close()
                    response.release_conn()

        except S3Error as e:
            if e.code == 'NoSuchKey':
                raise NotFoundError(f"Package not found: {package}")
            logger.error(
                "package_retrieval_failed",
                package=str(package),
                error=str(e)
            )
            raise StorageReadError(f"Failed to read package: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    async def put(self, package: PackageIdentifier, reader: BinaryIO) -> int:
        """Put a package into storage."""
        self._validate_package(package)
        object_name = self._get_object_name(package)

        # Check if exists first
        try:
            if await self.exists(package):
                raise AlreadyExistsError(f"Package already exists: {package}")
        except S3Error as e:
            if e.code != 'NoSuchKey':
                raise MinioStorageError(f"Failed to check existence: {e}")

        # Buffer the data since we need size and MinIO needs seekable stream
        buffer = io.BytesIO()
        size = 0
        while chunk := reader.read(8192):
            size += len(chunk)
            buffer.write(chunk)
        buffer.seek(0)

        try:
            # Store the package
            self.client.put_object(
                bucket_name=self.bucket,
                object_name=object_name,
                data=buffer,
                length=size,
                content_type='application/octet-stream'
            )

            # Create and store metadata
            metadata = PackageMetadata(
                name=package.name,
                version=package.version,
                sha=package.sha,
                size=size,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            await self._save_metadata(package, metadata)

            logger.info(
                "package_stored",
                package=str(package),
                size=size
            )
            return size

        except S3Error as e:
            logger.error(
                "package_storage_failed",
                package=str(package),
                error=str(e)
            )
            raise StorageWriteError(f"Failed to store package: {e}")
        finally:
            buffer.close()

    async def _save_metadata(self, package: PackageIdentifier, metadata: PackageMetadata) -> None:
        """Save package metadata."""
        metadata_name = self._get_metadata_name(package)
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
            metadata_json = json.dumps(metadata_dict, indent=2)
            metadata_bytes = metadata_json.encode('utf-8')
            
            self.client.put_object(
                bucket_name=self.bucket,
                object_name=metadata_name,
                data=io.BytesIO(metadata_bytes),
                length=len(metadata_bytes),
                content_type='application/json'
            )
        except S3Error as e:
            raise MinioStorageError(f"Failed to save metadata: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    async def exists(self, package: PackageIdentifier) -> bool:
        """Check if a package exists."""
        self._validate_package(package)
        try:
            self.client.stat_object(
                bucket_name=self.bucket,
                object_name=self._get_object_name(package)
            )
            return True
        except S3Error as e:
            if e.code == 'NoSuchKey':
                return False
            raise MinioStorageError(f"Failed to check existence: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    async def delete(self, package: PackageIdentifier) -> None:
        """Delete a package."""
        self._validate_package(package)
        object_name = self._get_object_name(package)
        metadata_name = self._get_metadata_name(package)

        try:
            # Delete package and metadata
            self.client.remove_object(self.bucket, object_name)
            try:
                self.client.remove_object(self.bucket, metadata_name)
            except S3Error:
                pass  # Ignore metadata deletion errors
            logger.info("package_deleted", package=str(package))
        except S3Error as e:
            if e.code == 'NoSuchKey':
                raise NotFoundError(f"Package not found: {package}")
            logger.error(
                "package_deletion_failed",
                package=str(package),
                error=str(e)
            )
            raise MinioStorageError(f"Failed to delete package: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    async def get_metadata(self, package: PackageIdentifier) -> PackageMetadata:
        """Get package metadata."""
        self._validate_package(package)
        object_name = self._get_object_name(package)
        metadata_name = self._get_metadata_name(package)

        try:
            try:
                # Try to get metadata file first
                response = self.client.get_object(
                    bucket_name=self.bucket,
                    object_name=metadata_name
                )
                metadata_json = response.read().decode('utf-8')
                metadata_dict = json.loads(metadata_json)
                return PackageMetadata(**metadata_dict)
            except S3Error as e:
                if e.code != 'NoSuchKey':
                    raise

            # Fall back to generating from object stats
            stats = self.client.stat_object(
                bucket_name=self.bucket,
                object_name=object_name
            )
            return PackageMetadata(
                name=package.name,
                version=package.version,
                sha=package.sha,
                size=stats.size,
                created_at=stats.last_modified.astimezone(timezone.utc).isoformat(),
            )
        except S3Error as e:
            if e.code == 'NoSuchKey':
                raise NotFoundError(f"Package not found: {package}")
            raise MinioStorageError(f"Failed to get metadata: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    async def list_versions(self, name: str, version: str) -> List[PackageIdentifier]:
        """List all packages for a specific version."""
        prefix = f"{name}/{version}/"
        try:
            packages = []
            objects = self.client.list_objects(
                bucket_name=self.bucket,
                prefix=prefix,
                recursive=True
            )
            for obj in objects:
                # Skip metadata files
                if obj.object_name.endswith(self.metadata_suffix):
                    continue
                # Parse object name into package info
                parts = obj.object_name.split('/')
                if len(parts) == 3:
                    packages.append(PackageIdentifier(
                        name=parts[0],
                        version=parts[1],
                        sha=parts[2]
                    ))
            return packages
        except S3Error as e:
            raise MinioStorageError(f"Failed to list versions: {e}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    async def list_all_versions(self, name: str) -> List[str]:
        """List all versions of a package."""
        prefix = f"{name}/"
        try:
            versions = set()
            objects = self.client.list_objects(
                bucket_name=self.bucket,
                prefix=prefix,
                recursive=True
            )
            for obj in objects:
                parts = obj.object_name.split('/')
                if len(parts) >= 2:
                    versions.add(parts[1])
            return sorted(list(versions))
        except S3Error as e:
            raise MinioStorageError(f"Failed to list all versions: {e}")

    async def cleanup(self) -> None:
        """Clean up any resources."""
        # No cleanup needed for MinIO storage
        await super().cleanup()