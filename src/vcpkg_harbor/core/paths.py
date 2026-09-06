"""Well-known URL paths, route names and mount-prefix helpers.

Kept in one place because the application factory mounts them and the dashboard
templates link to them. Every path here is relative to the application root, so
it still has to be resolved through :func:`vcpkg_harbor.dashboard.urls.url_path`
before it ends up in a template.

The helpers translate between the two path flavours that show up once the
application is served under a prefix: the *request* path, which may or may not
carry the prefix depending on how the reverse proxy is configured, and the
*route* path the endpoints are registered with.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.requests import Request

#: Mount point and route name of the bundled static files.
STATIC_URL_PATH = "/static"
STATIC_ROUTE_NAME = "static"

#: Interactive API documentation and schema, as configured on the FastAPI app.
API_DOCS_PATH = "/api/docs"
API_REDOC_PATH = "/api/redoc"
API_OPENAPI_PATH = "/api/openapi.json"

#: ASGI scope key holding the prefix the application is mounted under.
ROOT_PATH_KEY = "root_path"
#: Separator between path segments, and the path of the application root.
PATH_SEPARATOR = "/"
APP_ROOT_PATH = "/"


def normalize_prefix(root_path: str) -> str:
    """Return a mount prefix without its trailing slash.

    ``""`` and ``"/"`` both mean "mounted at the domain root" and normalise to
    the empty string, so callers can concatenate the result unconditionally.
    """
    return root_path.rstrip(PATH_SEPARATOR)


def has_prefix(path: str, root_path: str) -> bool:
    """Whether ``path`` already starts with the mount prefix.

    Compares whole segments, so ``/harbormaster`` is not treated as living under
    the ``/harbor`` prefix.
    """
    prefix = normalize_prefix(root_path)
    if not prefix:
        return True
    return path == prefix or path.startswith(f"{prefix}{PATH_SEPARATOR}")


def strip_prefix(path: str, root_path: str) -> str:
    """Return ``path`` without the mount prefix, i.e. the registered route path.

    A reverse proxy that forwards the prefix verbatim sends
    ``/harbor/packages``, one that strips it sends ``/packages``; both map onto
    ``/packages``, which is how the route is registered.
    """
    prefix = normalize_prefix(root_path)
    if prefix and has_prefix(path, root_path):
        return path[len(prefix) :] or APP_ROOT_PATH
    return path


def route_path(request: "Request") -> str:
    """Return the path of the current request as the routes declare it."""
    return strip_prefix(request.url.path, request.scope.get(ROOT_PATH_KEY, ""))
