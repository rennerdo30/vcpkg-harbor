"""Storage backend registry with entry points discovery."""

import sys
from typing import TYPE_CHECKING

import structlog

from vcpkg_harbor.core.exceptions import StorageConfigurationError

if TYPE_CHECKING:
    from vcpkg_harbor.core.config import Settings
    from vcpkg_harbor.storage.base import StorageBackend

if sys.version_info >= (3, 12):
    from importlib.metadata import entry_points
else:
    from importlib.metadata import entry_points

logger = structlog.get_logger(__name__)

# Registry of storage backends
_backends: dict[str, type["StorageBackend"]] = {}

ENTRY_POINT_GROUP = "vcpkg_harbor.storage"


def discover_backends() -> dict[str, type["StorageBackend"]]:
    """Discover storage backends via entry points."""
    global _backends

    if _backends:
        return _backends

    eps = entry_points(group=ENTRY_POINT_GROUP)

    for ep in eps:
        try:
            backend_class = ep.load()
            _backends[ep.name] = backend_class
            logger.debug("Discovered storage backend", name=ep.name, cls=backend_class.__name__)
        except Exception as e:
            logger.warning("Failed to load storage backend", name=ep.name, error=str(e))

    return _backends


def register_backend(name: str, backend_class: type["StorageBackend"]) -> None:
    """Register a storage backend manually.

    This is useful for testing or adding backends without entry points.
    """
    _backends[name] = backend_class
    logger.debug("Registered storage backend", name=name, cls=backend_class.__name__)


def list_storage_backends() -> list[str]:
    """List all available storage backend names."""
    discover_backends()
    return list(_backends.keys())


def get_storage_backend(settings: "Settings") -> "StorageBackend":
    """Get an initialized storage backend based on settings.

    Args:
        settings: Application settings

    Returns:
        Configured storage backend instance

    Raises:
        StorageConfigurationError: If the backend type is not found
    """
    discover_backends()

    backend_type = settings.storage.type
    backend_config = settings.get_storage_config()

    if backend_type not in _backends:
        available = list(_backends.keys())
        raise StorageConfigurationError(
            f"Unknown storage backend: {backend_type}. Available backends: {available}"
        )

    backend_class = _backends[backend_type]
    logger.info(
        "Creating storage backend", type=backend_type, config_keys=list(backend_config.keys())
    )

    return backend_class(**backend_config)
