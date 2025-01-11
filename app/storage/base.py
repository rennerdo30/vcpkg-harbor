from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import BinaryIO, Optional, List, Dict, Any, Protocol
import structlog

logger = structlog.get_logger(__name__)

class StorageError(Exception):
    """Base class for all storage-related errors."""
    pass

class AlreadyExistsError(StorageError):
    """Raised when attempting to store an item that already exists."""
    pass

class NotFoundError(StorageError):
    """Raised when an item is not found in storage."""
    pass

class StorageWriteError(StorageError):
    """Raised when writing to storage fails."""
    pass

class StorageReadError(StorageError):
    """Raised when reading from storage fails."""
    pass

@dataclass
class PackageMetadata:
    """Package metadata."""
    name: str
    version: str
    sha: str
    size: int
    created_at: str
    content_type: str = "application/octet-stream"
    extra: Dict[str, Any] = None

    def __post_init__(self):
        if self.extra is None:
            self.extra = {}

@dataclass
class PackageIdentifier:
    """Package identifier."""
    name: str
    version: str
    sha: str

    def __str__(self) -> str:
        return f"{self.name}/{self.version}/{self.sha}"

    def get_path(self) -> str:
        """Get the storage path for this package."""
        return str(self)

class StorageBackend(Protocol):
    """Protocol defining the interface for storage backends."""
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the storage backend.
        
        Should be called before any other operations.
        
        Raises:
            StorageError: If initialization fails
        """
        pass

    @abstractmethod
    async def get(self, package: PackageIdentifier, writer: BinaryIO) -> None:
        """Get a package from storage.
        
        Args:
            package: Package identifier
            writer: Binary writer to receive the package data
            
        Raises:
            NotFoundError: If package doesn't exist
            StorageReadError: If reading fails
            StorageError: For other errors
        """
        pass

    @abstractmethod
    async def put(self, package: PackageIdentifier, reader: BinaryIO) -> int:
        """Put a package into storage.
        
        Args:
            package: Package identifier
            reader: Binary reader for package data
            
        Returns:
            int: Size of stored package in bytes
            
        Raises:
            AlreadyExistsError: If package already exists
            StorageWriteError: If writing fails
            StorageError: For other errors
        """
        pass

    @abstractmethod
    async def exists(self, package: PackageIdentifier) -> bool:
        """Check if a package exists.
        
        Args:
            package: Package identifier
            
        Returns:
            bool: True if package exists
            
        Raises:
            StorageError: If check fails
        """
        pass

    @abstractmethod
    async def delete(self, package: PackageIdentifier) -> None:
        """Delete a package.
        
        Args:
            package: Package identifier
            
        Raises:
            NotFoundError: If package doesn't exist
            StorageError: If deletion fails
        """
        pass

    @abstractmethod
    async def get_metadata(self, package: PackageIdentifier) -> PackageMetadata:
        """Get package metadata.
        
        Args:
            package: Package identifier
            
        Returns:
            PackageMetadata: Package metadata
            
        Raises:
            NotFoundError: If package doesn't exist
            StorageError: If metadata retrieval fails
        """
        pass

    @abstractmethod
    async def list_versions(self, name: str, version: str) -> List[PackageIdentifier]:
        """List all packages for a specific version.
        
        Args:
            name: Package name
            version: Package version
            
        Returns:
            List[PackageIdentifier]: List of package identifiers
            
        Raises:
            StorageError: If listing fails
        """
        pass

    @abstractmethod
    async def list_all_versions(self, name: str) -> List[str]:
        """List all versions of a package.
        
        Args:
            name: Package name
            
        Returns:
            List[str]: List of version strings
            
        Raises:
            StorageError: If listing fails
        """
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """Clean up temporary resources.
        
        Should be called when shutting down.
        """
        pass

class BaseStorageBackend(StorageBackend):
    """Base implementation of StorageBackend with common functionality."""

    async def initialize(self) -> None:
        """Default initialization."""
        logger.info("initializing_storage", backend=self.__class__.__name__)

    async def cleanup(self) -> None:
        """Default cleanup."""
        logger.info("cleaning_up_storage", backend=self.__class__.__name__)

    async def exists(self, package: PackageIdentifier) -> bool:
        """Default implementation checking via get_metadata."""
        try:
            await self.get_metadata(package)
            return True
        except NotFoundError:
            return False
        except StorageError as e:
            logger.error("exists_check_failed", package=str(package), error=str(e))
            raise

    async def list_versions(self, name: str, version: str) -> List[PackageIdentifier]:
        """Default implementation - may be overridden for better performance."""
        raise NotImplementedError("list_versions not supported by this backend")

    async def list_all_versions(self, name: str) -> List[str]:
        """Default implementation - may be overridden for better performance."""
        raise NotImplementedError("list_all_versions not supported by this backend")

    async def get_metadata(self, package: PackageIdentifier) -> PackageMetadata:
        """Default implementation using stat-like info."""
        raise NotImplementedError("get_metadata not supported by this backend")

    def _validate_package(self, package: PackageIdentifier) -> None:
        """Validate package identifier.
        
        Raises:
            ValueError: If package identifier is invalid
        """
        if not package.name or not package.version or not package.sha:
            raise ValueError("Package name, version, and sha are required")
        
        # Add any additional validation as needed
        
        if len(package.sha) < 8:  # Example validation
            raise ValueError("SHA must be at least 8 characters long")