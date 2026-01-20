"""Dashboard routes for web UI."""

from pathlib import Path
from typing import TYPE_CHECKING, cast

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

if TYPE_CHECKING:
    from vcpkg_harbor.services.package_service import PackageService
    from vcpkg_harbor.services.stats_service import StatsService

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["dashboard"])

# Set up templates
TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


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

    recent_packages = await package_service.get_recent_packages(limit=5)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "cache_stats": cache_stats,
            "request_stats": request_stats,
            "uptime": uptime,
            "recent_packages": recent_packages,
        },
    )


@router.get("/packages", response_class=HTMLResponse)
async def packages_list(request: Request) -> HTMLResponse:
    """Render the packages list page."""
    stats_service = get_stats_service(request)
    package_service = get_package_service(request)

    cache_stats = await stats_service.get_cache_stats()
    uptime = stats_service.get_uptime_human()

    # Get query parameters
    search = request.query_params.get("search", "")
    page = int(request.query_params.get("page", 1))
    limit = 20
    offset = (page - 1) * limit

    if search:
        packages = await package_service.search_packages(search, limit=limit)
    else:
        packages = await package_service.get_package_summaries(limit=limit, offset=offset)

    return templates.TemplateResponse(
        "packages.html",
        {
            "request": request,
            "packages": packages,
            "search": search,
            "page": page,
            "limit": limit,
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

    versions = await package_service.get_package_versions(name, limit=50)

    if not versions:
        return templates.TemplateResponse(
            "404.html",
            {
                "request": request,
                "message": f"Package '{name}' not found",
                "cache_stats": cache_stats,
                "uptime": uptime,
            },
            status_code=404,
        )

    total_size = sum(v.size for v in versions)

    return templates.TemplateResponse(
        "package_detail.html",
        {
            "request": request,
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

    largest_packages = await package_service.get_largest_packages(limit=10)

    return templates.TemplateResponse(
        "stats.html",
        {
            "request": request,
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
        "partials/stats_summary.html",
        {
            "request": request,
            "cache_stats": cache_stats,
            "request_stats": request_stats,
        },
    )


@router.get("/partials/recent-packages", response_class=HTMLResponse)
async def recent_packages_partial(request: Request) -> HTMLResponse:
    """Render recent packages partial for HTMX updates."""
    package_service = get_package_service(request)

    recent_packages = await package_service.get_recent_packages(limit=5)

    return templates.TemplateResponse(
        "partials/recent_packages.html",
        {
            "request": request,
            "recent_packages": recent_packages,
        },
    )
