"""Cache API endpoints for vcpkg binary protocol."""

import time
from typing import Any, AsyncIterator

import structlog
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from vcpkg_harbor.core.dependencies import CacheServiceDep, StatsServiceDep
from vcpkg_harbor.core.exceptions import (
    PackageAlreadyExistsError,
    PackageNotFoundError,
    StorageError,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["cache"])


@router.head("/{name}/{version}/{sha}/{triplet}")
async def check_package(
    name: str,
    version: str,
    sha: str,
    triplet: str,
    cache_service: CacheServiceDep,
    stats_service: StatsServiceDep,
) -> Response:
    """Check if a package exists in the cache.

    This endpoint is used by vcpkg to check if a binary package
    is available before attempting to download it.

    Args:
        name: Package name
        version: Package version
        sha: Package SHA hash
        cache_service: Injected cache service
        stats_service: Injected stats service

    Returns:
        200 OK if package exists
        404 Not Found if package doesn't exist
    """
    start_time = time.time()

    try:
        exists = await cache_service.check_exists(name, version, sha, triplet)

        if exists:
            stats_service.record_cache_hit()
            stats_service.record_head_request(success=True)

            # Get package info for headers
            try:
                info = await cache_service.get_package_info(name, version, sha, triplet)
                response = Response(status_code=200)
                response.headers["Content-Length"] = str(info.size)
                if info.etag:
                    response.headers["ETag"] = info.etag
                return response
            except Exception:
                return Response(status_code=200)
        else:
            stats_service.record_cache_miss()
            stats_service.record_head_request(success=False)
            raise HTTPException(status_code=404, detail="Package not found")

    except HTTPException:
        raise
    except Exception as e:
        stats_service.record_error()
        logger.error("Error checking package", name=name, version=version, sha=sha, triplet=triplet, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        elapsed = (time.time() - start_time) * 1000
        stats_service.record_request_time(elapsed)


@router.get("/{name}/{version}/{sha}/{triplet}")
async def download_package(
    name: str,
    version: str,
    sha: str,
    triplet: str,
    cache_service: CacheServiceDep,
    stats_service: StatsServiceDep,
) -> StreamingResponse:
    """Download a package from the cache.

    This endpoint streams the binary package content to the client.

    Args:
        name: Package name
        version: Package version
        sha: Package SHA hash
        cache_service: Injected cache service
        stats_service: Injected stats service

    Returns:
        Streaming binary response with package content
    """
    start_time = time.time()

    try:
        # Get package info for headers
        try:
            info = await cache_service.get_package_info(name, version, sha, triplet)
            headers = {
                "Content-Length": str(info.size),
                "Content-Type": "application/octet-stream",
            }
            if info.etag:
                headers["ETag"] = info.etag
        except PackageNotFoundError:
            stats_service.record_cache_miss()
            stats_service.record_error()
            raise HTTPException(status_code=404, detail="Package not found")

        # Stream the package content
        async def stream_package() -> AsyncIterator[bytes]:
            try:
                async for chunk in cache_service.get_package(name, version, sha, triplet):
                    yield chunk
                stats_service.record_download()
                stats_service.record_cache_hit()
            except Exception as e:
                logger.error("Error streaming package", error=str(e))
                stats_service.record_error()

        return StreamingResponse(
            stream_package(),
            media_type="application/octet-stream",
            headers=headers,
        )

    except HTTPException:
        raise
    except PackageNotFoundError:
        stats_service.record_cache_miss()
        raise HTTPException(status_code=404, detail="Package not found")
    except Exception as e:
        stats_service.record_error()
        logger.error("Error downloading package", name=name, version=version, sha=sha, triplet=triplet, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        elapsed = (time.time() - start_time) * 1000
        stats_service.record_request_time(elapsed)


@router.put("/{name}/{version}/{sha}/{triplet}")
async def upload_package(
    name: str,
    version: str,
    sha: str,
    triplet: str,
    request: Request,
    cache_service: CacheServiceDep,
    stats_service: StatsServiceDep,
) -> dict[str, Any]:
    """Upload a package to the cache.

    This endpoint receives a binary package and stores it in the cache.

    Args:
        name: Package name
        version: Package version
        sha: Package SHA hash
        triplet: Target triplet (e.g., x64-linux, x64-windows)
        request: FastAPI request object
        cache_service: Injected cache service
        stats_service: Injected stats service

    Returns:
        JSON response with upload status and details
    """
    start_time = time.time()

    try:
        # Get content length if available
        content_length = request.headers.get("content-length")
        size = int(content_length) if content_length else None

        # Stream the request body
        async def request_stream() -> AsyncIterator[bytes]:
            async for chunk in request.stream():
                yield chunk

        # Store the package
        package_info = await cache_service.put_package(
            name, version, sha, triplet, request_stream(), size
        )

        stats_service.record_upload()

        return {
            "status": "success",
            "name": name,
            "version": version,
            "sha": sha,
            "triplet": triplet,
            "size": package_info.size,
            "etag": package_info.etag,
        }

    except PackageAlreadyExistsError:
        stats_service.record_error()
        raise HTTPException(status_code=409, detail="Package already exists")
    except StorageError as e:
        stats_service.record_error()
        if "read-only" in str(e).lower():
            raise HTTPException(status_code=403, detail="Server is in read-only mode")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        stats_service.record_error()
        logger.error("Error uploading package", name=name, version=version, sha=sha, triplet=triplet, error=str(e))
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    finally:
        elapsed = (time.time() - start_time) * 1000
        stats_service.record_request_time(elapsed)


@router.delete("/{name}/{version}/{sha}/{triplet}")
async def delete_package(
    name: str,
    version: str,
    sha: str,
    triplet: str,
    cache_service: CacheServiceDep,
    stats_service: StatsServiceDep,
) -> dict[str, Any]:
    """Delete a package from the cache.

    This endpoint removes a package from the cache.

    Args:
        name: Package name
        version: Package version
        sha: Package SHA hash
        cache_service: Injected cache service
        stats_service: Injected stats service

    Returns:
        JSON response with deletion status
    """
    start_time = time.time()

    try:
        deleted = await cache_service.delete_package(name, version, sha, triplet)

        if deleted:
            return {"status": "deleted", "name": name, "version": version, "sha": sha, "triplet": triplet}
        else:
            raise HTTPException(status_code=404, detail="Package not found")

    except HTTPException:
        raise
    except StorageError as e:
        stats_service.record_error()
        if "read-only" in str(e).lower():
            raise HTTPException(status_code=403, detail="Server is in read-only mode")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        stats_service.record_error()
        logger.error("Error deleting package", name=name, version=version, sha=sha, triplet=triplet, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        elapsed = (time.time() - start_time) * 1000
        stats_service.record_request_time(elapsed)
