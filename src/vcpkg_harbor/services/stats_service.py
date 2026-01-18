"""Statistics service for monitoring and metrics."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from vcpkg_harbor.storage.base import StorageBackend

logger = structlog.get_logger(__name__)


@dataclass
class CacheStats:
    """Statistics about the cache."""

    total_packages: int = 0
    total_size_bytes: int = 0
    unique_package_names: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    uploads: int = 0
    downloads: int = 0
    errors: int = 0
    backend_type: str = ""
    last_updated: datetime = field(default_factory=datetime.utcnow)

    @property
    def total_size_human(self) -> str:
        """Get human-readable total size."""
        size = self.total_size_bytes
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} PB"

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return (self.cache_hits / total) * 100


@dataclass
class RequestStats:
    """Statistics about requests."""

    total_requests: int = 0
    head_requests: int = 0
    get_requests: int = 0
    put_requests: int = 0
    delete_requests: int = 0
    success_count: int = 0
    error_count: int = 0
    avg_response_time_ms: float = 0.0
    requests_per_minute: float = 0.0
    start_time: datetime = field(default_factory=datetime.utcnow)


class StatsService:
    """Service for collecting and reporting statistics."""

    def __init__(self, storage: "StorageBackend") -> None:
        """Initialize the stats service.

        Args:
            storage: Storage backend instance
        """
        self.storage = storage
        self._cache_hits = 0
        self._cache_misses = 0
        self._uploads = 0
        self._downloads = 0
        self._errors = 0
        self._request_count = 0
        self._request_times: list[float] = []
        self._head_requests = 0
        self._get_requests = 0
        self._put_requests = 0
        self._delete_requests = 0
        self._success_count = 0
        self._error_count = 0
        self._start_time = datetime.utcnow()

    def record_cache_hit(self) -> None:
        """Record a cache hit."""
        self._cache_hits += 1
        logger.debug("Cache hit recorded", total_hits=self._cache_hits)

    def record_cache_miss(self) -> None:
        """Record a cache miss."""
        self._cache_misses += 1
        logger.debug("Cache miss recorded", total_misses=self._cache_misses)

    def record_upload(self) -> None:
        """Record a successful upload."""
        self._uploads += 1
        self._put_requests += 1
        self._success_count += 1

    def record_download(self) -> None:
        """Record a successful download."""
        self._downloads += 1
        self._get_requests += 1
        self._success_count += 1

    def record_head_request(self, success: bool = True) -> None:
        """Record a HEAD request."""
        self._head_requests += 1
        if success:
            self._success_count += 1
        else:
            self._error_count += 1

    def record_error(self) -> None:
        """Record an error."""
        self._errors += 1
        self._error_count += 1

    def record_request_time(self, time_ms: float) -> None:
        """Record a request processing time."""
        self._request_count += 1
        self._request_times.append(time_ms)
        # Keep only last 1000 times for rolling average
        if len(self._request_times) > 1000:
            self._request_times.pop(0)

    async def get_cache_stats(self) -> CacheStats:
        """Get current cache statistics."""
        try:
            storage_stats = await self.storage.get_stats()

            return CacheStats(
                total_packages=storage_stats.get("total_packages", 0),
                total_size_bytes=storage_stats.get("total_size_bytes", 0),
                unique_package_names=storage_stats.get("unique_package_names", 0),
                cache_hits=self._cache_hits,
                cache_misses=self._cache_misses,
                uploads=self._uploads,
                downloads=self._downloads,
                errors=self._errors,
                backend_type=storage_stats.get("backend", "unknown"),
                last_updated=datetime.utcnow(),
            )
        except Exception as e:
            logger.error("Error getting cache stats", error=str(e))
            return CacheStats(
                cache_hits=self._cache_hits,
                cache_misses=self._cache_misses,
                uploads=self._uploads,
                downloads=self._downloads,
                errors=self._errors,
                backend_type="error",
            )

    def get_request_stats(self) -> RequestStats:
        """Get current request statistics."""
        avg_time = 0.0
        if self._request_times:
            avg_time = sum(self._request_times) / len(self._request_times)

        # Calculate requests per minute
        uptime = (datetime.utcnow() - self._start_time).total_seconds()
        rpm = 0.0
        if uptime > 0:
            rpm = (self._request_count / uptime) * 60

        return RequestStats(
            total_requests=self._request_count,
            head_requests=self._head_requests,
            get_requests=self._get_requests,
            put_requests=self._put_requests,
            delete_requests=self._delete_requests,
            success_count=self._success_count,
            error_count=self._error_count,
            avg_response_time_ms=avg_time,
            requests_per_minute=rpm,
            start_time=self._start_time,
        )

    def get_uptime(self) -> timedelta:
        """Get server uptime."""
        return datetime.utcnow() - self._start_time

    def get_uptime_human(self) -> str:
        """Get human-readable uptime."""
        uptime = self.get_uptime()
        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        if seconds or not parts:
            parts.append(f"{seconds}s")

        return " ".join(parts)
