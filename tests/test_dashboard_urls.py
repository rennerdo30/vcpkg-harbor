"""Tests for serving the dashboard under a sub-path and inside an iframe.

The dashboard must not emit URLs that are absolute to the *browser's* root: those
break as soon as the app is mounted behind a reverse proxy prefix or embedded in
another page. Everything here guards that property.
"""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from vcpkg_harbor.app import create_app
from vcpkg_harbor.core.config import ProxySettings, Settings
from vcpkg_harbor.core.paths import has_prefix, route_path, strip_prefix
from vcpkg_harbor.dashboard.urls import (
    HTMX_CDN_URL,
    TAILWIND_CDN_URL,
    VENDORED_HTMX_JS,
    VENDORED_TAILWIND_CSS,
    url_path,
)

TEST_STORAGE_PATH = "/tmp/vcpkg-harbor-test-urls"
PACKAGE_DIR = Path(__file__).parent.parent / "src" / "vcpkg_harbor"
STATIC_DIR = PACKAGE_DIR / "static"
TEMPLATE_DIR = PACKAGE_DIR / "dashboard" / "templates"

#: Prefix used for the "behind a reverse proxy" cases.
ROOT_PATH = "/harbor"
#: Pages and partials that make up the dashboard.
DASHBOARD_PATHS = (
    "/",
    "/packages",
    "/stats",
    "/partials/stats-summary",
    "/partials/recent-packages",
    "/partials/packages",
)
#: Attributes in the rendered HTML that carry a URL.
URL_ATTRIBUTE_PATTERN = re.compile(r'(?:href|src|action|hx-get|hx-post)="([^"]+)"')


def make_settings(*, assets: str | None = None, **proxy: object) -> Settings:
    """Build test settings with optional dashboard asset and proxy overrides."""
    dashboard: dict[str, object] = {"enabled": True}
    if assets is not None:
        dashboard["assets"] = assets
    return Settings(
        server={"host": "127.0.0.1", "port": 15151},
        storage={"type": "filesystem", "path": TEST_STORAGE_PATH},
        logging={"level": "DEBUG", "file": None},
        dashboard=dashboard,
        metrics={"enabled": False},
        auth={"enabled": False},
        proxy=proxy,
    )


@contextmanager
def make_client(**overrides: object) -> Iterator[TestClient]:
    """Yield a test client for an app configured with ``overrides``."""
    Path(TEST_STORAGE_PATH).mkdir(parents=True, exist_ok=True)
    with TestClient(create_app(make_settings(**overrides))) as client:
        yield client


@pytest.fixture
def root_client() -> Iterator[TestClient]:
    """Client for an app mounted at the domain root."""
    with make_client() as client:
        yield client


@pytest.fixture
def prefixed_client() -> Iterator[TestClient]:
    """Client for an app mounted under :data:`ROOT_PATH`."""
    with make_client(root_path=ROOT_PATH) as client:
        yield client


def collected_urls(html: str) -> list[str]:
    """Return every URL referenced by the rendered page."""
    return URL_ATTRIBUTE_PATTERN.findall(html)


def local_urls(html: str) -> list[str]:
    """Return the referenced URLs that point at this application."""
    return [url for url in collected_urls(html) if not url.startswith(("http", "#", "mailto:"))]


# --- Settings ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", ""),
        ("/", ""),
        ("harbor", "/harbor"),
        ("/harbor", "/harbor"),
        ("/harbor/", "/harbor"),
        ("  /harbor/  ", "/harbor"),
        ("/team/harbor", "/team/harbor"),
    ],
)
def test_root_path_is_normalised(raw: str, expected: str) -> None:
    """A prefix is stored as '' or '/segment' regardless of how it was written."""
    assert ProxySettings(_env_file=None, root_path=raw).root_path == expected


def test_proxy_defaults_keep_todays_behaviour() -> None:
    """By default nothing is prefixed and no framing header is sent."""
    settings = ProxySettings(_env_file=None)
    assert settings.root_path == ""
    assert settings.frame_ancestors is None
    assert settings.frame_options is None


@pytest.mark.parametrize("value", ["deny", "SAMEORIGIN", " sameorigin "])
def test_frame_options_accepts_known_values(value: str) -> None:
    """Valid X-Frame-Options values are normalised to upper case."""
    assert ProxySettings(_env_file=None, frame_options=value).frame_options == value.strip().upper()


def test_frame_options_rejects_unknown_values() -> None:
    """A typo in the header value fails fast instead of shipping a broken header."""
    with pytest.raises(ValueError, match="Invalid frame_options"):
        ProxySettings(_env_file=None, frame_options="ALLOW-FROM https://example.com")


# --- URL generation ---------------------------------------------------------


def test_pages_render_at_the_domain_root(root_client: TestClient) -> None:
    """Without a prefix every dashboard path still renders."""
    for path in DASHBOARD_PATHS:
        assert root_client.get(path).status_code == 200, path


def test_pages_render_under_a_prefix(prefixed_client: TestClient) -> None:
    """With a prefix-stripping proxy in front, the same routes still match."""
    for path in DASHBOARD_PATHS:
        assert prefixed_client.get(path).status_code == 200, path


def test_pages_render_when_the_proxy_keeps_the_prefix(prefixed_client: TestClient) -> None:
    """A proxy that forwards the prefix verbatim also reaches the routes."""
    for path in DASHBOARD_PATHS:
        response = prefixed_client.get(f"{ROOT_PATH}{path}".replace("//", "/"))
        assert response.status_code == 200, path


@pytest.mark.parametrize("path", DASHBOARD_PATHS)
def test_every_url_carries_the_prefix(prefixed_client: TestClient, path: str) -> None:
    """No rendered URL may resolve against the iframe or proxy root."""
    html = prefixed_client.get(path).text
    offenders = [url for url in local_urls(html) if not url.startswith(f"{ROOT_PATH}/")]
    assert offenders == [], offenders


@pytest.mark.parametrize("path", DASHBOARD_PATHS)
def test_urls_stay_clean_without_a_prefix(root_client: TestClient, path: str) -> None:
    """Mounting at the root must not gain a stray prefix."""
    html = root_client.get(path).text
    offenders = [url for url in local_urls(html) if url.startswith("//") or ROOT_PATH in url]
    assert offenders == [], offenders


def test_navigation_links_and_active_state(prefixed_client: TestClient) -> None:
    """The nav links are prefixed and the current page is marked as active."""
    html = prefixed_client.get("/packages").text
    assert f'href="{ROOT_PATH}/packages"' in html
    assert f'href="{ROOT_PATH}/stats"' in html
    assert 'aria-current="page"' in html


def test_htmx_endpoints_are_prefixed(prefixed_client: TestClient) -> None:
    """The polling panels must call the prefixed partial endpoints."""
    html = prefixed_client.get("/").text
    assert f'hx-get="{ROOT_PATH}/partials/stats-summary"' in html
    assert f'hx-get="{ROOT_PATH}/partials/recent-packages"' in html


def test_package_links_are_prefixed(prefixed_client: TestClient) -> None:
    """Links built from route parameters are prefixed as well."""
    html = prefixed_client.get("/partials/packages").text
    assert f'href="{ROOT_PATH}/packages' in html or "Nothing cached yet" in html


def test_binary_source_snippet_includes_the_prefix(prefixed_client: TestClient) -> None:
    """The VCPKG_BINARY_SOURCES snippet points at the prefixed cache endpoint."""
    html = prefixed_client.get("/").text
    assert f"{ROOT_PATH}/{{name}}/{{version}}/{{sha}}/{{triplet}}" in html


def test_missing_package_page_links_back_with_the_prefix(prefixed_client: TestClient) -> None:
    """Even the 404 page's buttons stay inside the application."""
    response = prefixed_client.get("/packages/does-not-exist")
    assert response.status_code == 404
    assert f'href="{ROOT_PATH}/packages"' in response.text


def _fake_request(app: FastAPI, root_path: str = "") -> Request:
    """Build a minimal request for the pure URL helpers."""
    return Request({"type": "http", "app": app, "root_path": root_path, "headers": []})


def test_url_path_resolves_route_names_and_literal_paths() -> None:
    """Route names and literal application paths both gain the prefix."""
    app = create_app(make_settings(root_path=ROOT_PATH))
    request = _fake_request(app, ROOT_PATH)
    assert url_path(request, "packages_list") == f"{ROOT_PATH}/packages"
    assert url_path(request, "package_detail", name="fmt") == f"{ROOT_PATH}/packages/fmt"
    assert url_path(request, "/api/docs") == f"{ROOT_PATH}/api/docs"


def test_url_path_is_a_no_op_without_a_prefix() -> None:
    """At the domain root the helper returns the plain route path."""
    app = create_app(make_settings())
    assert url_path(_fake_request(app), "packages_list") == "/packages"


def test_unknown_route_names_fall_back_to_the_application_root() -> None:
    """A template referring to a missing route renders a link, not a traceback."""
    app = create_app(make_settings(root_path=ROOT_PATH))
    assert url_path(_fake_request(app, ROOT_PATH), "no_such_route") == f"{ROOT_PATH}/"


@pytest.mark.parametrize(
    ("forwarded_path", "expected"),
    [
        (f"{ROOT_PATH}/packages", "/packages"),
        ("/packages", "/packages"),
        (ROOT_PATH, "/"),
    ],
)
def test_route_path_strips_the_prefix(forwarded_path: str, expected: str) -> None:
    """Both proxy styles map onto the path the routes are registered with."""
    scope = {
        "type": "http",
        "root_path": ROOT_PATH,
        "path": forwarded_path,
        "headers": [],
        "query_string": b"",
        "scheme": "http",
        "server": ("testserver", 80),
    }
    assert route_path(Request(scope)) == expected


@pytest.mark.parametrize(
    ("path", "prefix", "expected"),
    [
        ("/harbor/packages", ROOT_PATH, True),
        ("/harbor", ROOT_PATH, True),
        # Only whole segments count, or /harbormaster would look prefixed.
        ("/harbormaster", ROOT_PATH, False),
        ("/packages", ROOT_PATH, False),
        ("/packages", "", True),
    ],
)
def test_has_prefix_compares_whole_segments(path: str, prefix: str, expected: bool) -> None:
    """A prefix only matches on a segment boundary."""
    assert has_prefix(path, prefix) is expected


def test_strip_prefix_leaves_unprefixed_paths_alone() -> None:
    """Nothing is removed when the path does not carry the prefix."""
    assert strip_prefix("/packages", ROOT_PATH) == "/packages"
    assert strip_prefix("/harbormaster", ROOT_PATH) == "/harbormaster"


# --- Assets -----------------------------------------------------------------


def test_vendored_assets_are_shipped() -> None:
    """The vendored Tailwind and HTMX builds must be part of the package."""
    for relative in (VENDORED_TAILWIND_CSS, VENDORED_HTMX_JS):
        asset = STATIC_DIR / relative
        assert asset.is_file(), asset
        assert asset.stat().st_size > 0


def test_local_assets_are_served_and_referenced(prefixed_client: TestClient) -> None:
    """By default the dashboard loads its assets from itself, not from a CDN."""
    html = prefixed_client.get("/").text
    assert f"{ROOT_PATH}/static/{VENDORED_TAILWIND_CSS}" in html
    assert f"{ROOT_PATH}/static/{VENDORED_HTMX_JS}" in html
    assert "cdn.jsdelivr.net" not in html
    assert "unpkg.com" not in html


def test_cdn_assets_can_be_opted_into() -> None:
    """Setting dashboard.assets = 'cdn' switches to the pinned CDN builds."""
    with make_client(assets="cdn") as client:
        html = client.get("/").text
    assert TAILWIND_CDN_URL in html
    assert HTMX_CDN_URL in html
    assert VENDORED_HTMX_JS not in html


@pytest.mark.parametrize("prefix", ["", ROOT_PATH])
def test_static_files_are_served_whether_or_not_the_proxy_keeps_the_prefix(
    prefixed_client: TestClient, prefix: str
) -> None:
    """A mounted StaticFiles app resolves the file under both proxy layouts.

    Starlette derives the file name by removing the mount's ``root_path`` from
    the request path, which silently fails when a prefix-stripping proxy leaves
    the prefix out. RootPathMiddleware puts it back.
    """
    for relative in (VENDORED_TAILWIND_CSS, VENDORED_HTMX_JS, "logo.svg", "favicon.svg"):
        response = prefixed_client.get(f"{prefix}/static/{relative}")
        assert response.status_code == 200, f"{prefix}/static/{relative}"
        assert response.content


def test_static_files_are_served_at_the_domain_root(root_client: TestClient) -> None:
    """Without a prefix the static mount keeps working as before."""
    assert root_client.get("/static/logo.svg").status_code == 200


def test_prefix_is_not_doubled_when_the_proxy_keeps_it(prefixed_client: TestClient) -> None:
    """A path that already carries the prefix is passed through untouched."""
    assert prefixed_client.get(f"{ROOT_PATH}{ROOT_PATH}/packages").status_code == 404
    html = prefixed_client.get(f"{ROOT_PATH}/packages").text
    assert f'href="{ROOT_PATH}/stats"' in html
    assert f"{ROOT_PATH}{ROOT_PATH}" not in html


@pytest.mark.parametrize("path", DASHBOARD_PATHS)
def test_local_assets_avoid_inline_scripts_and_styles(root_client: TestClient, path: str) -> None:
    """Nothing inline, so a strict Content-Security-Policy still renders the page."""
    html = root_client.get(path).text
    assert "<script>" not in html
    assert "<style" not in html
    assert "style=" not in html


def test_htmx_indicator_styles_are_disabled(root_client: TestClient) -> None:
    """HTMX must not inject its indicator stylesheet; static/css/style.css has it.

    The injection is an inline ``<style>`` element, which is exactly what a
    strict ``style-src`` blocks.
    """
    html = root_client.get("/").text
    assert '<meta name="htmx-config" content=\'{"includeIndicatorStyles": false}\'>' in html
    style_css = (STATIC_DIR / "css" / "style.css").read_text(encoding="utf-8")
    assert ".htmx-indicator" in style_css


def test_no_template_hardcodes_a_root_absolute_url() -> None:
    """Guard for templates added later: links must go through url_path().

    A literal ``href="/packages"`` resolves against the browser's root, which is
    the embedding page's origin rather than this application.
    """
    offenders: list[str] = []
    for template in sorted(TEMPLATE_DIR.rglob("*.html")):
        for number, line in enumerate(template.read_text(encoding="utf-8").splitlines(), start=1):
            for match in URL_ATTRIBUTE_PATTERN.finditer(line):
                url = match.group(1)
                if url.startswith("/") and "url_path(" not in url:
                    offenders.append(f"{template.name}:{number}: {url}")
    assert offenders == [], offenders


# --- Framing headers --------------------------------------------------------


def test_no_framing_headers_by_default(root_client: TestClient) -> None:
    """Embedding stays possible out of the box."""
    response = root_client.get("/")
    assert "x-frame-options" not in response.headers
    assert "content-security-policy" not in response.headers


def test_frame_ancestors_header_is_sent_when_configured() -> None:
    """A configured frame-ancestors value ends up in the CSP header."""
    with make_client(frame_ancestors="'self' https://intranet.example.com") as client:
        response = client.get("/")
        assert (
            response.headers["content-security-policy"]
            == "frame-ancestors 'self' https://intranet.example.com"
        )
        # Cache endpoints are not HTML, but a uniform policy is simpler to reason
        # about and vcpkg ignores the header.
        assert "content-security-policy" in client.get("/health").headers


def test_frame_options_header_is_sent_when_configured() -> None:
    """The legacy header is available for scanners that still require it."""
    with make_client(frame_options="SAMEORIGIN") as client:
        assert client.get("/").headers["x-frame-options"] == "SAMEORIGIN"


def test_frame_headers_reach_an_auth_rejection() -> None:
    """The headers are applied outside auth, so even a 401 carries them."""
    settings = Settings(
        server={"host": "127.0.0.1", "port": 15151},
        storage={"type": "filesystem", "path": TEST_STORAGE_PATH},
        logging={"level": "DEBUG", "file": None},
        dashboard={"enabled": True},
        metrics={"enabled": False},
        auth={"enabled": True, "type": "token", "token": "secret"},
        proxy={"frame_options": "SAMEORIGIN"},
    )
    Path(TEST_STORAGE_PATH).mkdir(parents=True, exist_ok=True)
    with TestClient(create_app(settings)) as client:
        response = client.get("/pkg/1.0/abc/x64-linux")
        assert response.status_code == 401
        assert response.headers["x-frame-options"] == "SAMEORIGIN"


# --- Other routers ----------------------------------------------------------


def test_api_and_health_routes_work_under_a_prefix(prefixed_client: TestClient) -> None:
    """The docs and health endpoints are reachable with and without the prefix."""
    assert prefixed_client.get("/health").status_code == 200
    assert prefixed_client.get(f"{ROOT_PATH}/health").status_code == 200
    assert prefixed_client.get("/api/openapi.json").status_code == 200


def test_openapi_declares_the_prefix(prefixed_client: TestClient) -> None:
    """Generated clients must target the prefixed server URL."""
    schema = prefixed_client.get("/api/openapi.json").json()
    assert schema["servers"][0]["url"] == ROOT_PATH


def test_authenticated_dashboard_stays_public_behind_a_prefix() -> None:
    """Public paths are matched on the route path, not the forwarded path."""
    settings = Settings(
        server={"host": "127.0.0.1", "port": 15151},
        storage={"type": "filesystem", "path": TEST_STORAGE_PATH},
        logging={"level": "DEBUG", "file": None},
        dashboard={"enabled": True},
        metrics={"enabled": False},
        auth={"enabled": True, "type": "token", "token": "secret"},
        proxy={"root_path": ROOT_PATH},
    )
    Path(TEST_STORAGE_PATH).mkdir(parents=True, exist_ok=True)
    with TestClient(create_app(settings)) as client:
        # Prefix kept by the proxy: still recognised as the public health route.
        assert client.get(f"{ROOT_PATH}/health").status_code == 200
        assert client.get(f"{ROOT_PATH}/static/{VENDORED_HTMX_JS}").status_code == 200
        # A cache path still requires the token.
        assert client.get(f"{ROOT_PATH}/pkg/1.0/abc/x64-linux").status_code == 401
