"""Package service for managing and querying packages."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from vcpkg_harbor.storage.base import PackageInfo

if TYPE_CHECKING:
    from vcpkg_harbor.storage.base import StorageBackend

logger = structlog.get_logger(__name__)


@dataclass
class PackageVersion:
    """Information about a specific package version."""

    name: str
    version: str
    sha: str
    size: int
    created_at: str | None = None

    @classmethod
    def from_package_info(cls, info: PackageInfo) -> "PackageVersion":
        """Create from PackageInfo."""
        return cls(
            name=info.name,
            version=info.version,
            sha=info.sha,
            size=info.size,
            created_at=info.created_at.isoformat() if info.created_at else None,
        )


@dataclass
class PackageSummary:
    """Summary information about a package."""

    name: str
    version_count: int
    total_size: int
    latest_version: str | None = None
    versions: list[str] | None = None


class PackageService:
    """Service for querying package information."""

    def __init__(self, storage: "StorageBackend") -> None:
        """Initialize the package service.

        Args:
            storage: Storage backend instance
        """
        self.storage = storage

    async def list_packages(
        self,
        prefix: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PackageInfo]:
        """List packages with optional filtering.

        Args:
            prefix: Optional prefix to filter packages
            limit: Maximum number of packages to return
            offset: Number of packages to skip

        Returns:
            List of PackageInfo objects
        """
        logger.debug("Listing packages", prefix=prefix, limit=limit, offset=offset)
        return await self.storage.list_packages(prefix=prefix, limit=limit, offset=offset)

    async def get_package_summaries(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PackageSummary]:
        """Get summaries of all packages grouped by name.

        Args:
            limit: Maximum number of unique packages to return
            offset: Number of packages to skip

        Returns:
            List of PackageSummary objects
        """
        logger.debug("Getting package summaries", limit=limit, offset=offset)

        # Get all packages (no limit for grouping)
        all_packages = await self.storage.list_packages()

        # Group by name
        package_groups: dict[str, list[PackageInfo]] = {}
        for pkg in all_packages:
            if pkg.name not in package_groups:
                package_groups[pkg.name] = []
            package_groups[pkg.name].append(pkg)

        # Create summaries
        summaries = []
        sorted_names = sorted(package_groups.keys())

        for name in sorted_names[offset : offset + limit]:
            packages = package_groups[name]
            versions = list({p.version for p in packages})

            # Sort versions (try semver-like sorting)
            versions.sort(reverse=True)

            summaries.append(
                PackageSummary(
                    name=name,
                    version_count=len(versions),
                    total_size=sum(p.size for p in packages),
                    latest_version=versions[0] if versions else None,
                    versions=versions[:5],  # Top 5 versions
                )
            )

        return summaries

    async def get_package_versions(
        self,
        name: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PackageVersion]:
        """Get all versions of a specific package.

        Args:
            name: Package name
            limit: Maximum number of versions to return
            offset: Number of versions to skip

        Returns:
            List of PackageVersion objects
        """
        logger.debug("Getting package versions", name=name, limit=limit, offset=offset)

        # Get packages with name prefix
        packages = await self.storage.list_packages(prefix=f"{name}/")

        # Filter to exact name match and convert to versions
        versions = []
        for pkg in packages:
            if pkg.name == name:
                versions.append(PackageVersion.from_package_info(pkg))

        # Sort by version (newest first)
        versions.sort(key=lambda v: v.version, reverse=True)

        return versions[offset : offset + limit]

    async def search_packages(
        self,
        query: str,
        limit: int = 50,
    ) -> list[PackageSummary]:
        """Search packages by name.

        Args:
            query: Search query (partial name match)
            limit: Maximum number of results

        Returns:
            List of matching PackageSummary objects
        """
        logger.debug("Searching packages", query=query, limit=limit)

        # Get all summaries and filter
        all_summaries = await self.get_package_summaries(limit=1000)

        # Filter by query
        query_lower = query.lower()
        matching = [s for s in all_summaries if query_lower in s.name.lower()]

        return matching[:limit]

    async def get_recent_packages(
        self,
        limit: int = 10,
    ) -> list[PackageInfo]:
        """Get recently added/updated packages.

        Args:
            limit: Maximum number of packages to return

        Returns:
            List of recently added packages
        """
        logger.debug("Getting recent packages", limit=limit)

        # Get all packages and sort by creation date
        packages = await self.storage.list_packages(limit=limit * 3)

        # Sort by creation date (newest first)
        packages.sort(key=lambda p: p.created_at or "", reverse=True)

        return packages[:limit]

    async def get_largest_packages(
        self,
        limit: int = 10,
    ) -> list[PackageInfo]:
        """Get the largest packages by size.

        Args:
            limit: Maximum number of packages to return

        Returns:
            List of largest packages
        """
        logger.debug("Getting largest packages", limit=limit)

        # Get all packages
        packages = await self.storage.list_packages()

        # Sort by size (largest first)
        packages.sort(key=lambda p: p.size, reverse=True)

        return packages[:limit]
