"""ASGI middleware for serving behind a reverse proxy and for framing headers.

:class:`RootPathMiddleware` makes the two common reverse proxy layouts behave
identically. :class:`FrameHeadersMiddleware` adds the optional headers that
restrict who may embed the dashboard in an ``<iframe>``; embedding needs no
header at all, which stays the default.

Both are plain ASGI middleware rather than ``BaseHTTPMiddleware`` so cache
uploads and downloads keep streaming through untouched.
"""

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from vcpkg_harbor.core.paths import has_prefix, normalize_prefix

logger = structlog.get_logger(__name__)

#: Header used to restrict which pages may embed a response in a frame.
CSP_HEADER = "content-security-policy"
#: Legacy framing header, still honoured by some browsers and scanners.
FRAME_OPTIONS_HEADER = "x-frame-options"
#: CSP directive that expresses the framing policy.
FRAME_ANCESTORS_DIRECTIVE = "frame-ancestors"
#: ASGI message type carrying the response status and headers.
RESPONSE_START = "http.response.start"
#: ASGI scope type this middleware applies to.
HTTP_SCOPE = "http"
#: ASGI scope types that carry a request path.
PATH_SCOPE_TYPES = frozenset({"http", "websocket"})
#: ASGI scope keys holding the decoded and the original request path.
PATH_KEY = "path"
RAW_PATH_KEY = "raw_path"
#: Encoding of the ASGI ``raw_path``.
RAW_PATH_ENCODING = "latin-1"


class RootPathMiddleware:
    """Ensure the request path carries the prefix the app is mounted under.

    Two reverse proxy layouts lead to the same application. One forwards the
    prefixed path verbatim (``/harbor/packages``); the other strips the prefix
    and announces it out of band (``/packages`` plus ``--root-path /harbor``).
    Starlette's routing handles both, but a *mounted* sub-application - the
    ``/static`` mount - resolves the file it should serve by removing the mount's
    ``root_path`` from the request path, so with a prefix-stripping proxy it
    looks for ``static/logo.svg`` inside the static directory and answers 404.

    Restoring the prefix here removes the difference: from this point inwards the
    path always looks the way a prefix-preserving proxy would have sent it.
    """

    def __init__(self, app: ASGIApp, root_path: str = "") -> None:
        """Initialise the middleware.

        Args:
            app: The ASGI application to wrap.
            root_path: The prefix the application is served under, e.g.
                ``"/harbor"``. An empty value disables the middleware.
        """
        self.app = app
        self.root_path = normalize_prefix(root_path)
        logger.debug("Root path middleware configured", root_path=self.root_path)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Prepend the mount prefix to the request path when it is missing."""
        if not self.root_path or scope["type"] not in PATH_SCOPE_TYPES:
            await self.app(scope, receive, send)
            return

        path: str = scope.get(PATH_KEY, "")
        if has_prefix(path, self.root_path):
            await self.app(scope, receive, send)
            return

        scope = dict(scope)
        scope[PATH_KEY] = f"{self.root_path}{path}"
        raw_path = scope.get(RAW_PATH_KEY)
        if isinstance(raw_path, bytes):
            scope[RAW_PATH_KEY] = self.root_path.encode(RAW_PATH_ENCODING) + raw_path
        logger.debug(
            "Restored mount prefix on request path",
            root_path=self.root_path,
            original_path=path,
            path=scope[PATH_KEY],
        )
        await self.app(scope, receive, send)


class FrameHeadersMiddleware:
    """Add configured framing headers to every HTTP response."""

    def __init__(
        self,
        app: ASGIApp,
        frame_ancestors: str | None = None,
        frame_options: str | None = None,
    ) -> None:
        """Initialise the middleware.

        Args:
            app: The ASGI application to wrap.
            frame_ancestors: ``frame-ancestors`` value, e.g. ``"'self'"``.
            frame_options: ``X-Frame-Options`` value, e.g. ``"SAMEORIGIN"``.
        """
        self.app = app
        self.frame_ancestors = frame_ancestors
        self.frame_options = frame_options
        logger.debug(
            "Frame headers middleware configured",
            frame_ancestors=frame_ancestors,
            frame_options=frame_options,
        )

    @property
    def enabled(self) -> bool:
        """Whether the middleware has anything to add."""
        return bool(self.frame_ancestors or self.frame_options)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Wrap ``send`` so response headers can be extended."""
        if scope["type"] != HTTP_SCOPE or not self.enabled:
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == RESPONSE_START:
                headers = MutableHeaders(scope=message)
                if self.frame_ancestors and CSP_HEADER not in headers:
                    headers[CSP_HEADER] = f"{FRAME_ANCESTORS_DIRECTIVE} {self.frame_ancestors}"
                if self.frame_options and FRAME_OPTIONS_HEADER not in headers:
                    headers[FRAME_OPTIONS_HEADER] = self.frame_options
            await send(message)

        await self.app(scope, receive, send_with_headers)
