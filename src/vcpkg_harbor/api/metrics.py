"""Prometheus metrics endpoint."""

import structlog
from fastapi import APIRouter, Request, Response

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def prometheus_metrics(request: Request) -> Response:
    """Prometheus metrics endpoint.

    Returns metrics in Prometheus text format.

    Returns:
        Plain text Prometheus metrics
    """
    try:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

        # Get our custom metrics
        stats_service = request.app.state.stats_service
        storage = request.app.state.storage

        # Update gauges with current values
        cache_stats = await stats_service.get_cache_stats()
        request_stats = stats_service.get_request_stats()

        # Generate Prometheus output
        metrics_output = generate_latest()

        return Response(content=metrics_output, media_type=CONTENT_TYPE_LATEST)

    except ImportError:
        logger.warning("prometheus_client not installed")
        return Response(
            content="# Prometheus client not installed\n",
            media_type="text/plain",
        )
    except Exception as e:
        logger.error("Error generating metrics", error=str(e))
        return Response(
            content=f"# Error generating metrics: {e}\n",
            media_type="text/plain",
            status_code=500,
        )


def setup_prometheus_metrics() -> None:
    """Set up Prometheus metrics collectors."""
    try:
        from prometheus_client import Counter, Gauge, Histogram

        # Define metrics
        global CACHE_HITS, CACHE_MISSES, UPLOADS, DOWNLOADS, ERRORS
        global PACKAGE_COUNT, STORAGE_SIZE, REQUEST_LATENCY

        CACHE_HITS = Counter(
            "vcpkg_harbor_cache_hits_total",
            "Total number of cache hits",
        )

        CACHE_MISSES = Counter(
            "vcpkg_harbor_cache_misses_total",
            "Total number of cache misses",
        )

        UPLOADS = Counter(
            "vcpkg_harbor_uploads_total",
            "Total number of package uploads",
        )

        DOWNLOADS = Counter(
            "vcpkg_harbor_downloads_total",
            "Total number of package downloads",
        )

        ERRORS = Counter(
            "vcpkg_harbor_errors_total",
            "Total number of errors",
        )

        PACKAGE_COUNT = Gauge(
            "vcpkg_harbor_packages_total",
            "Total number of packages in cache",
        )

        STORAGE_SIZE = Gauge(
            "vcpkg_harbor_storage_bytes",
            "Total storage size in bytes",
        )

        REQUEST_LATENCY = Histogram(
            "vcpkg_harbor_request_latency_seconds",
            "Request latency in seconds",
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        )

        logger.info("Prometheus metrics initialized")

    except ImportError:
        logger.warning("prometheus_client not installed, metrics disabled")
