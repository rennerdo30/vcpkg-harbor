"""FastAPI dependency injection utilities."""

from functools import lru_cache
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Request

from vcpkg_harbor.core.config import Settings, get_settings
from vcpkg_harbor.core.logging import get_logger

if TYPE_CHECKING:
    from vcpkg_harbor.services.cache_service import CacheService
    from vcpkg_harbor.services.stats_service import StatsService
    from vcpkg_harbor.storage.base import StorageBackend


def get_settings_dep() -> Settings:
    """Dependency for getting settings."""
    return get_settings()


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


def get_storage(request: Request) -> "StorageBackend":
    """Get the storage backend from app state."""
    return request.app.state.storage


StorageDep = Annotated["StorageBackend", Depends(get_storage)]


def get_cache_service(request: Request) -> "CacheService":
    """Get the cache service from app state."""
    return request.app.state.cache_service


CacheServiceDep = Annotated["CacheService", Depends(get_cache_service)]


def get_stats_service(request: Request) -> "StatsService":
    """Get the stats service from app state."""
    return request.app.state.stats_service


StatsServiceDep = Annotated["StatsService", Depends(get_stats_service)]


@lru_cache
def get_logger_dep(name: str = "vcpkg-harbor"):
    """Get a logger dependency."""
    return get_logger(name)
