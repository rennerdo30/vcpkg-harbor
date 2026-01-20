"""Authentication middleware for vcpkg-harbor."""

from typing import Awaitable, Callable, TYPE_CHECKING

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.types import ASGIApp

    from vcpkg_harbor.auth.providers import AuthProvider

logger = structlog.get_logger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware for authenticating requests."""

    # Paths that don't require authentication
    PUBLIC_PATHS = {
        "/health",
        "/health/live",
        "/health/ready",
        "/health/details",
        "/metrics",
    }

    # Path prefixes that don't require authentication
    PUBLIC_PREFIXES = {
        "/static/",
    }

    def __init__(
        self,
        app: "ASGIApp",
        provider: "AuthProvider",
        exclude_dashboard: bool = True,
    ) -> None:
        """Initialize auth middleware.

        Args:
            app: The ASGI application
            provider: Authentication provider to use
            exclude_dashboard: If True, dashboard routes don't require auth
        """
        super().__init__(app)
        self.provider = provider
        self.exclude_dashboard = exclude_dashboard

    def _is_public_path(self, path: str) -> bool:
        """Check if path is public (doesn't require auth)."""
        # Exact matches
        if path in self.PUBLIC_PATHS:
            return True

        # Prefix matches
        for prefix in self.PUBLIC_PREFIXES:
            if path.startswith(prefix):
                return True

        # Dashboard paths (if excluded)
        if self.exclude_dashboard:
            if path == "/" or path.startswith("/packages") or path.startswith("/stats"):
                return True
            if path.startswith("/partials/"):
                return True

        return False

    async def dispatch(
        self, request: "Request", call_next: Callable[["Request"], Awaitable["Response"]]
    ) -> "Response":
        """Process the request and check authentication."""
        path = request.url.path

        # Skip auth for public paths
        if self._is_public_path(path):
            return await call_next(request)

        # Authenticate the request
        if not await self.provider.authenticate(request):
            logger.warning(
                "Authentication failed",
                path=path,
                method=request.method,
                client=request.client.host if request.client else "unknown",
            )
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Add user info to request state
        request.state.user = self.provider.get_user(request)

        return await call_next(request)
