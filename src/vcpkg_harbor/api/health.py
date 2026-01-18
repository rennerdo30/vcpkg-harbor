"""Health check endpoints."""

from datetime import datetime
from typing import TYPE_CHECKING

import structlog
from fastapi import APIRouter, Request

from vcpkg_harbor import __version__

if TYPE_CHECKING:
    from vcpkg_harbor.storage.base import StorageBackend

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["health"])


def get_storage(request: Request) -> "StorageBackend":
    """Get storage backend from request state."""
    return request.app.state.storage


@router.get("/health")
async def health_check(request: Request) -> dict:
    """Basic health check endpoint.

    Returns the overall health status of the service.
    Used by load balancers and orchestrators.

    Returns:
        JSON with health status and basic info
    """
    storage = get_storage(request)
    storage_healthy = await storage.health_check()

    status = "healthy" if storage_healthy else "degraded"

    return {
        "status": status,
        "version": __version__,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/health/ready")
async def readiness_check(request: Request) -> dict:
    """Readiness check endpoint.

    Indicates whether the service is ready to handle requests.
    Returns 200 if ready, 503 if not ready.

    Returns:
        JSON with readiness status and component states
    """
    storage = get_storage(request)

    checks = {
        "storage": await storage.health_check(),
    }

    all_ready = all(checks.values())

    if not all_ready:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "checks": checks,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    return {
        "status": "ready",
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/health/live")
async def liveness_check() -> dict:
    """Liveness check endpoint.

    Indicates whether the service is alive and running.
    This is a simple check that doesn't verify external dependencies.

    Returns:
        JSON with liveness status
    """
    return {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/health/details")
async def health_details(request: Request) -> dict:
    """Detailed health check endpoint.

    Returns comprehensive health information including
    storage stats and system information.

    Returns:
        JSON with detailed health information
    """
    storage = get_storage(request)
    stats_service = request.app.state.stats_service

    storage_healthy = await storage.health_check()
    storage_stats = await storage.get_stats()

    cache_stats = await stats_service.get_cache_stats()
    request_stats = stats_service.get_request_stats()
    uptime = stats_service.get_uptime_human()

    return {
        "status": "healthy" if storage_healthy else "degraded",
        "version": __version__,
        "uptime": uptime,
        "timestamp": datetime.utcnow().isoformat(),
        "storage": {
            "healthy": storage_healthy,
            "backend": storage_stats.get("backend", "unknown"),
            "total_packages": storage_stats.get("total_packages", 0),
            "total_size_bytes": storage_stats.get("total_size_bytes", 0),
        },
        "cache": {
            "hits": cache_stats.cache_hits,
            "misses": cache_stats.cache_misses,
            "hit_rate": f"{cache_stats.hit_rate:.1f}%",
            "uploads": cache_stats.uploads,
            "downloads": cache_stats.downloads,
        },
        "requests": {
            "total": request_stats.total_requests,
            "success_rate": f"{(request_stats.success_count / max(request_stats.total_requests, 1) * 100):.1f}%",
            "avg_response_time_ms": f"{request_stats.avg_response_time_ms:.2f}",
            "requests_per_minute": f"{request_stats.requests_per_minute:.2f}",
        },
    }
