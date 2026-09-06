"""FastAPI application factory for vcpkg-harbor."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from vcpkg_harbor import __version__
from vcpkg_harbor.api import cache_router, health_router, metrics_router
from vcpkg_harbor.auth import (
    AuthMiddleware,
    AuthProvider,
    BasicAuthProvider,
    NoAuthProvider,
    TokenAuthProvider,
)
from vcpkg_harbor.core.config import Settings, get_settings
from vcpkg_harbor.core.logging import setup_logging
from vcpkg_harbor.core.middleware import FrameHeadersMiddleware, RootPathMiddleware
from vcpkg_harbor.core.paths import (
    API_DOCS_PATH,
    API_OPENAPI_PATH,
    API_REDOC_PATH,
    STATIC_ROUTE_NAME,
    STATIC_URL_PATH,
)
from vcpkg_harbor.dashboard import router as dashboard_router
from vcpkg_harbor.services import CacheService, PackageService, StatsService, TagService
from vcpkg_harbor.storage.registry import get_storage_backend

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager."""
    settings: Settings = app.state.settings

    logger.info(
        "Starting vcpkg-harbor",
        version=__version__,
        host=settings.server.host,
        port=settings.server.port,
        storage_type=settings.storage.type,
    )

    # Initialize storage backend
    storage = get_storage_backend(settings)
    await storage.initialize()
    app.state.storage = storage

    logger.info(
        "Storage backend initialized",
        type=settings.storage.type,
    )

    # Initialize services
    tag_service = TagService(storage, settings)
    app.state.tag_service = tag_service
    app.state.cache_service = CacheService(storage, settings, tag_service)
    app.state.stats_service = StatsService(storage)
    app.state.package_service = PackageService(storage)

    # Log startup info
    if settings.server.read_only:
        logger.info("Server running in READ-ONLY mode")
    if settings.server.write_only:
        logger.info("Server running in WRITE-ONLY mode")
    if settings.tags.enabled:
        logger.info(
            "Build tags enabled",
            default_namespace=settings.tags.default_namespace,
            dedupe=settings.tags.dedupe,
            allowlist=sorted(settings.tags.allowlist) or None,
            max_packages_per_tag=settings.tags.max_packages_per_tag or None,
            max_bytes_per_tag=settings.tags.max_bytes_per_tag or None,
        )
    else:
        logger.info("Build tags disabled")

    yield

    # Cleanup
    logger.info("Shutting down vcpkg-harbor")
    await storage.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        settings: Optional settings instance. If not provided, uses get_settings().

    Returns:
        Configured FastAPI application
    """
    if settings is None:
        settings = get_settings()

    # Set up logging
    setup_logging(settings)

    # Create FastAPI app. root_path makes every generated URL (docs, dashboard
    # links, HTMX endpoints) include the prefix the app is served under.
    app = FastAPI(
        title="vcpkg-harbor",
        description="Binary cache server for vcpkg with plugin-based storage backends",
        version=__version__,
        lifespan=lifespan,
        docs_url=API_DOCS_PATH,
        redoc_url=API_REDOC_PATH,
        openapi_url=API_OPENAPI_PATH,
        root_path=settings.proxy.root_path,
    )

    # Store settings in app state
    app.state.settings = settings

    # Middleware, innermost first: add_middleware() puts each new layer outside
    # the previous one, so the request path is normalised before anything else
    # inspects it and the framing headers reach even an auth rejection.

    # Set up authentication if enabled
    if settings.auth.enabled:
        if settings.auth.type == "token" and settings.auth.token:
            provider: AuthProvider = TokenAuthProvider(settings.auth.token)
            logger.info("Token authentication enabled")
        elif settings.auth.type == "basic" and settings.auth.basic_users:
            provider = BasicAuthProvider.from_string(settings.auth.basic_users)
            logger.info("Basic authentication enabled")
        else:
            provider = NoAuthProvider()
            logger.warning("Auth enabled but no valid provider configured, falling back to no auth")

        app.add_middleware(
            AuthMiddleware,
            provider=provider,
            exclude_dashboard=True,
        )
    else:
        logger.debug("Authentication disabled")

    # Framing headers, if the deployment restricts who may embed the dashboard.
    # Without them any page may embed it, which is the historical behaviour.
    if settings.proxy.frame_ancestors or settings.proxy.frame_options:
        app.add_middleware(
            FrameHeadersMiddleware,
            frame_ancestors=settings.proxy.frame_ancestors,
            frame_options=settings.proxy.frame_options,
        )
        logger.info(
            "Frame headers enabled",
            frame_ancestors=settings.proxy.frame_ancestors,
            frame_options=settings.proxy.frame_options,
        )

    # Outermost layer: make a prefix-stripping proxy look like a prefix-keeping
    # one, so the /static mount resolves either way.
    if settings.proxy.root_path:
        app.add_middleware(RootPathMiddleware, root_path=settings.proxy.root_path)

    # Include routers
    app.include_router(health_router)

    if settings.metrics.enabled:
        app.include_router(metrics_router)

    # Cache API routes (vcpkg protocol)
    app.include_router(cache_router)

    # Mount static files
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount(STATIC_URL_PATH, StaticFiles(directory=str(static_dir)), name=STATIC_ROUTE_NAME)

    # Dashboard routes
    if settings.dashboard.enabled:
        app.include_router(dashboard_router)

    logger.info(
        "Application configured",
        auth_enabled=settings.auth.enabled,
        metrics_enabled=settings.metrics.enabled,
        dashboard_enabled=settings.dashboard.enabled,
        root_path=settings.proxy.root_path or "/",
        dashboard_assets=settings.dashboard.assets,
    )

    return app
