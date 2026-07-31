"""Dashboard routes for web UI."""

from pathlib import Path
from typing import TYPE_CHECKING, cast

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from vcpkg_harbor.dashboard.filters import register_filters

if TYPE_CHECKING:
    from vcpkg_harbor.services.package_service import PackageService
    from vcpkg_harbor.services.stats_service import StatsService

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["dashboard"])

# Set up templates
TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
register_filters(templates.env)

# Listing sizes used by the dashboard pages.
PACKAGES_PER_PAGE = 20
RECENT_PACKAGES_LIMIT = 5
LARGEST_PACKAGES_LIMIT = 10
PACKAGE_VERSIONS_LIMIT = 50
FIRST_PAGE = 1


def get_stats_service(request: Request) -> "StatsService":
    """Get stats service from app state."""
    return cast("StatsService", request.app.state.stats_service)


def get_package_service(request: Request) -> "PackageService":
    """Get package service from app state."""
    return cast("PackageService", request.app.state.package_service)


@router.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request) -> HTMLResponse:
    """Render the dashboard home page."""
    stats_service = get_stats_service(request)
    package_service = get_package_service(request)

    cache_stats = await stats_service.get_cache_stats()
    request_stats = stats_service.get_request_stats()
    uptime = stats_service.get_uptime_human()

    recent_packages = await package_service.get_recent_packages(limit=RECENT_PACKAGES_LIMIT)

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "cache_stats": cache_stats,
            "request_stats": request_stats,
            "uptime": uptime,
            "recent_packages": recent_packages,
        },
    )


def _parse_page(raw_page: str) -> int:
    """Parse the ``page`` query parameter, falling back to the first page."""
    try:
        return max(FIRST_PAGE, int(raw_page))
    except ValueError:
        logger.debug("Ignoring invalid page parameter", page=raw_page)
        return FIRST_PAGE


async def _load_package_listing(request: Request) -> dict[str, object]:
    """Build the template context shared by the packages page and its partial."""
    package_service = get_package_service(request)

    search = request.query_params.get("search", "").strip()
    page = _parse_page(request.query_params.get("page", str(FIRST_PAGE)))
    offset = (page - FIRST_PAGE) * PACKAGES_PER_PAGE

    if search:
        packages = await package_service.search_packages(search, limit=PACKAGES_PER_PAGE)
    else:
        packages = await package_service.get_package_summaries(
            limit=PACKAGES_PER_PAGE, offset=offset
        )

    logger.debug("Loaded package listing", search=search, page=page, results=len(packages))
    return {
        "packages": packages,
        "search": search,
        "page": page,
        "limit": PACKAGES_PER_PAGE,
    }


@router.get("/packages", response_class=HTMLResponse)
async def packages_list(request: Request) -> HTMLResponse:
    """Render the packages list page."""
    stats_service = get_stats_service(request)

    cache_stats = await stats_service.get_cache_stats()
    uptime = stats_service.get_uptime_human()

    return templates.TemplateResponse(
        request,
        "packages.html",
        {
            **await _load_package_listing(request),
            "cache_stats": cache_stats,
            "uptime": uptime,
        },
    )


@router.get("/packages/{name}", response_class=HTMLResponse)
async def package_detail(request: Request, name: str) -> HTMLResponse:
    """Render the package detail page."""
    stats_service = get_stats_service(request)
    package_service = get_package_service(request)

    cache_stats = await stats_service.get_cache_stats()
    uptime = stats_service.get_uptime_human()

    versions = await package_service.get_package_versions(name, limit=PACKAGE_VERSIONS_LIMIT)

    if not versions:
        return templates.TemplateResponse(
            request,
            "404.html",
            {
                "message": f"Package '{name}' not found",
                "cache_stats": cache_stats,
                "uptime": uptime,
            },
            status_code=404,
        )

    total_size = sum(v.size for v in versions)

    return templates.TemplateResponse(
        request,
        "package_detail.html",
        {
            "name": name,
            "versions": versions,
            "total_size": total_size,
            "cache_stats": cache_stats,
            "uptime": uptime,
        },
    )


@router.get("/stats", response_class=HTMLResponse)
async def stats_page(request: Request) -> HTMLResponse:
    """Render the statistics page."""
    stats_service = get_stats_service(request)
    package_service = get_package_service(request)

    cache_stats = await stats_service.get_cache_stats()
    request_stats = stats_service.get_request_stats()
    uptime = stats_service.get_uptime_human()

    largest_packages = await package_service.get_largest_packages(limit=LARGEST_PACKAGES_LIMIT)

    return templates.TemplateResponse(
        request,
        "stats.html",
        {
            "cache_stats": cache_stats,
            "request_stats": request_stats,
            "uptime": uptime,
            "largest_packages": largest_packages,
        },
    )


# HTMX partial endpoints for dynamic updates


@router.get("/partials/stats-summary", response_class=HTMLResponse)
async def stats_summary_partial(request: Request) -> HTMLResponse:
    """Render stats summary partial for HTMX updates."""
    stats_service = get_stats_service(request)

    cache_stats = await stats_service.get_cache_stats()
    request_stats = stats_service.get_request_stats()

    return templates.TemplateResponse(
        request,
        "partials/stats_summary.html",
        {
            "cache_stats": cache_stats,
            "request_stats": request_stats,
        },
    )


@router.get("/partials/recent-packages", response_class=HTMLResponse)
async def recent_packages_partial(request: Request) -> HTMLResponse:
    """Render recent packages partial for HTMX updates."""
    package_service = get_package_service(request)

    recent_packages = await package_service.get_recent_packages(limit=RECENT_PACKAGES_LIMIT)

    return templates.TemplateResponse(
        request,
        "partials/recent_packages.html",
        {
            "recent_packages": recent_packages,
        },
    )


@router.get("/partials/packages", response_class=HTMLResponse)
async def packages_table_partial(request: Request) -> HTMLResponse:
    """Render the package table for HTMX-driven search-as-you-type."""
    return templates.TemplateResponse(
        request,
        "partials/package_table.html",
        await _load_package_listing(request),
    )
