"""URL and asset helpers for the dashboard templates.

The dashboard has to work when it is not served from a domain root: behind a
reverse proxy that mounts it under a prefix, and inside an ``<iframe>`` on
another page. Root-absolute links such as ``/packages`` resolve against the
*browser's* origin in both cases, which is why every link, asset and HTMX
endpoint in the templates goes through :func:`url_path`.

:func:`url_path` prepends the ASGI ``root_path`` (set from ``proxy.root_path``,
uvicorn's ``--root-path`` or a mounting parent application) to a route name or a
literal application path. It deliberately returns a path rather than the
absolute URL that ``request.url_for`` produces: a path cannot disagree with the
scheme or host the browser already uses, which matters when TLS is terminated at
the proxy.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from jinja2 import Environment, pass_context
from starlette.requests import Request
from starlette.routing import NoMatchFound

from vcpkg_harbor.core.paths import (
    API_DOCS_PATH,
    APP_ROOT_PATH,
    PATH_SEPARATOR,
    ROOT_PATH_KEY,
    STATIC_ROUTE_NAME,
    normalize_prefix,
    route_path,
)

if TYPE_CHECKING:
    from vcpkg_harbor.core.config import Settings

logger = structlog.get_logger(__name__)

#: Directory holding the bundled static files.
STATIC_DIR = Path(__file__).parent.parent / "static"
#: Tailwind source shared by the ahead-of-time build and the browser build.
TAILWIND_SOURCE_FILE = STATIC_DIR / "src" / "tailwind.css"
#: Vendored third-party assets, relative to the static directory.
VENDORED_TAILWIND_CSS = "vendor/tailwind.css"
VENDORED_HTMX_JS = "vendor/htmx.min.js"

#: Pinned CDN builds used when ``dashboard.assets`` is ``"cdn"``.
#: Keep the versions in step with scripts/build-dashboard-assets.sh.
TAILWIND_CDN_URL = "https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4.3.3"
HTMX_CDN_URL = "https://cdn.jsdelivr.net/npm/htmx.org@2.0.10/dist/htmx.min.js"

#: Value of ``dashboard.assets`` that selects the public CDNs.
ASSETS_CDN = "cdn"
#: Path used when a template asks for a route that is not registered.
FALLBACK_PATH = APP_ROOT_PATH
#: Name of the Jinja2 global exposing :func:`url_path` to templates.
URL_PATH_GLOBAL = "url_path"
#: Route name of the detailed health endpoint linked in the footer.
HEALTH_DETAILS_ROUTE = "health_details"
#: Directive stripped from the Tailwind source before the browser build sees it.
TAILWIND_SOURCE_DIRECTIVE = "@source"


@dataclass(frozen=True)
class NavItem:
    """One entry of the dashboard's main navigation.

    Attributes:
        label: Text shown in the navigation.
        route: Name of the route the entry links to.
        exact: Whether the entry is only highlighted on that exact path, as
            opposed to the path and everything below it.
    """

    label: str
    route: str
    exact: bool


#: The dashboard's main navigation, in display order.
NAV_ITEMS: tuple[NavItem, ...] = (
    NavItem(label="Dashboard", route="dashboard_home", exact=True),
    NavItem(label="Packages", route="packages_list", exact=False),
    NavItem(label="Statistics", route="stats_page", exact=True),
)


def url_path(request: Request, target: str, /, **params: Any) -> str:
    """Build an application-absolute URL path, honouring ``root_path``.

    Args:
        request: The current request, used for the mount prefix and routes.
        target: Either the name of a registered route (``"packages_list"``,
            ``"static"``) or a literal application path starting with ``/``.
        **params: Path parameters for the named route.

    Returns:
        A URL path including the application's mount prefix, e.g.
        ``/harbor/packages`` when the app is served under ``/harbor``.
    """
    root_path = normalize_prefix(request.scope.get(ROOT_PATH_KEY, ""))

    if target.startswith(PATH_SEPARATOR):
        path = target
    else:
        try:
            path = str(request.app.url_path_for(target, **params))
        except NoMatchFound:
            logger.warning("Template referenced an unknown route", route=target, params=params)
            path = FALLBACK_PATH

    return f"{root_path}{path}"


@lru_cache(maxsize=1)
def tailwind_browser_source() -> str:
    """Return the Tailwind source for the browser build, without ``@source``.

    Tailwind's browser build scans the live DOM, so the ``@source`` directives
    that steer the ahead-of-time build have nothing to point at; they are dropped
    to keep the browser console quiet.
    """
    try:
        source = TAILWIND_SOURCE_FILE.read_text(encoding="utf-8")
    except OSError as error:
        logger.error(
            "Cannot read Tailwind source", path=str(TAILWIND_SOURCE_FILE), error=str(error)
        )
        return ""
    lines = [
        line
        for line in source.splitlines()
        if not line.lstrip().startswith(TAILWIND_SOURCE_DIRECTIVE)
    ]
    return "\n".join(lines)


def cache_base_url(request: Request) -> str:
    """Return the absolute base URL of the application, without trailing slash.

    Used for the ``VCPKG_BINARY_SOURCES`` snippet, which vcpkg needs as an
    absolute URL. ``request.base_url`` already carries the mount prefix, and the
    scheme comes from ``X-Forwarded-Proto`` when uvicorn runs with
    ``--proxy-headers`` (which :mod:`vcpkg_harbor.__main__` enables).
    """
    return str(request.base_url).rstrip("/")


def navigation(request: Request) -> list[dict[str, Any]]:
    """Build the main navigation with prefixed links and the active entry marked.

    The active entry is decided on the route-relative path so it is correct no
    matter whether the proxy strips the prefix before forwarding.
    """
    current = route_path(request)
    items: list[dict[str, Any]] = []

    for item in NAV_ITEMS:
        try:
            target = str(request.app.url_path_for(item.route))
        except NoMatchFound:  # pragma: no cover - routes are registered together
            logger.warning("Navigation route is not registered", route=item.route)
            continue
        active = current == target if item.exact else current.startswith(target)
        items.append(
            {
                "label": item.label,
                "href": url_path(request, item.route),
                "active": active,
            }
        )

    return items


def template_context(request: Request) -> dict[str, Any]:
    """Context shared by every dashboard template.

    Used as a Starlette context processor so the pages and the HTMX partials all
    get the navigation, the API documentation link and the asset URLs without
    each route repeating itself.
    """
    settings: Settings = request.app.state.settings
    from_cdn = settings.dashboard.assets == ASSETS_CDN

    assets: dict[str, Any] = {
        "from_cdn": from_cdn,
        "htmx_js": HTMX_CDN_URL
        if from_cdn
        else url_path(request, STATIC_ROUTE_NAME, path=VENDORED_HTMX_JS),
    }
    if from_cdn:
        assets["tailwind_cdn"] = TAILWIND_CDN_URL
        assets["tailwind_source"] = tailwind_browser_source()
    else:
        assets["tailwind_css"] = url_path(request, STATIC_ROUTE_NAME, path=VENDORED_TAILWIND_CSS)

    return {
        "assets": assets,
        "nav_items": navigation(request),
        "api_docs_url": url_path(request, API_DOCS_PATH),
        "health_url": url_path(request, HEALTH_DETAILS_ROUTE),
        "cache_base_url": cache_base_url(request),
    }


def register_url_helpers(env: Environment) -> None:
    """Expose :func:`url_path` to templates as a request-aware global."""

    @pass_context
    def url_path_helper(context: dict[str, Any], target: str, /, **params: Any) -> str:
        return url_path(context["request"], target, **params)

    env.globals[URL_PATH_GLOBAL] = url_path_helper
    logger.debug("Registered dashboard URL helpers", helper=URL_PATH_GLOBAL)
