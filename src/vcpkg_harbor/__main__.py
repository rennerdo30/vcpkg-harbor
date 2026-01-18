"""Entry point for vcpkg-harbor CLI."""

import uvicorn

from vcpkg_harbor.core.config import get_settings
from vcpkg_harbor.core.logging import setup_logging


def main() -> None:
    """Run the vcpkg-harbor server."""
    settings = get_settings()
    setup_logging(settings)

    uvicorn.run(
        "vcpkg_harbor.app:create_app",
        factory=True,
        host=settings.server.host,
        port=settings.server.port,
        workers=settings.server.workers,
        reload=settings.server.reload,
        log_config=None,  # Use structlog instead
    )


if __name__ == "__main__":
    main()
