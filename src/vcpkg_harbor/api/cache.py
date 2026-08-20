"""Cache API endpoints for vcpkg binary protocol.

Two route shapes are served:

``/{name}/{version}/{sha}/{triplet}``
    The untagged routes, unchanged from before build tags existed.

``/{tag}/{name}/{version}/{sha}/{triplet}``
    The same operations scoped to a build tag. Because the tag is just a leading
    path segment, a client only appends it to the base URL it is configured
    with, for example ``x-azurl,https://harbor.example/nightly,,readwrite``.

Dashboard routes are one or two segments long, so neither shape collides with
them. Both shapes delegate to the same handlers below.
"""

import time
from collections.abc import AsyncIterator
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from vcpkg_harbor.core.dependencies import CacheServiceDep, StatsServiceDep
from vcpkg_harbor.core.exceptions import (
    InvalidTagError,
    PackageAlreadyExistsError,
    PackageNotFoundError,
    StorageError,
    TagsDisabledError,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["cache"])

# Path shapes served by this router.
UNTAGGED_PATH = "/{name}/{version}/{sha}/{triplet}"
TAGGED_PATH = "/{tag}" + UNTAGGED_PATH


def _reject_bad_tag(error: Exception) -> HTTPException:
    """Translate a tag error into an HTTP error.

    A malformed or non-allowlisted tag is a client mistake that must not
    silently create a new namespace, so it is reported as 400. When tags are
    switched off the tagged shape is not part of the API at all, so it is
    reported as 404.
    """
    if isinstance(error, TagsDisabledError):
        return HTTPException(status_code=404, detail="Build tags are disabled")
    return HTTPException(status_code=400, detail=str(error))


async def _check_package(
    cache_service: CacheServiceDep,
    stats_service: StatsServiceDep,
    name: str,
    version: str,
    sha: str,
    triplet: str,
    tag: str | None = None,
) -> Response:
    """Handle a HEAD request for both route shapes."""
    start_time = time.time()

    try:
        exists = await cache_service.check_exists(name, version, sha, triplet, tag=tag)

        if exists:
            stats_service.record_cache_hit()
            stats_service.record_head_request(success=True)

            # Get package info for headers
            try:
                info = await cache_service.get_package_info(name, version, sha, triplet, tag=tag)
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

    except (InvalidTagError, TagsDisabledError) as e:
        raise _reject_bad_tag(e)
    except HTTPException:
        raise
    except Exception as e:
        stats_service.record_error()
        logger.error(
            "Error checking package",
            tag=tag,
            name=name,
            version=version,
            sha=sha,
            triplet=triplet,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        elapsed = (time.time() - start_time) * 1000
        stats_service.record_request_time(elapsed)


async def _download_package(
    cache_service: CacheServiceDep,
    stats_service: StatsServiceDep,
    name: str,
    version: str,
    sha: str,
    triplet: str,
    tag: str | None = None,
) -> StreamingResponse:
    """Handle a GET request for both route shapes."""
    start_time = time.time()

    try:
        # Get package info for headers
        try:
            info = await cache_service.get_package_info(name, version, sha, triplet, tag=tag)
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
                async for chunk in cache_service.get_package(name, version, sha, triplet, tag=tag):
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

    except (InvalidTagError, TagsDisabledError) as e:
        raise _reject_bad_tag(e)
    except HTTPException:
        raise
    except PackageNotFoundError:
        stats_service.record_cache_miss()
        raise HTTPException(status_code=404, detail="Package not found")
    except Exception as e:
        stats_service.record_error()
        logger.error(
            "Error downloading package",
            tag=tag,
            name=name,
            version=version,
            sha=sha,
            triplet=triplet,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        elapsed = (time.time() - start_time) * 1000
        stats_service.record_request_time(elapsed)


async def _upload_package(
    request: Request,
    cache_service: CacheServiceDep,
    stats_service: StatsServiceDep,
    name: str,
    version: str,
    sha: str,
    triplet: str,
    tag: str | None = None,
) -> dict[str, Any]:
    """Handle a PUT request for both route shapes."""
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
        stored = await cache_service.put_package(
            name, version, sha, triplet, request_stream(), size, tag=tag
        )

        stats_service.record_upload()

        return {
            "status": "success",
            "name": name,
            "version": version,
            "sha": sha,
            "triplet": triplet,
            "size": stored.info.size,
            "etag": stored.info.etag,
            "tag": stored.tag,
            "namespace": stored.namespace,
            "deduplicated": stored.deduplicated,
            "evicted": stored.evicted,
        }

    except (InvalidTagError, TagsDisabledError) as e:
        raise _reject_bad_tag(e)
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
        logger.error(
            "Error uploading package",
            tag=tag,
            name=name,
            version=version,
            sha=sha,
            triplet=triplet,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    finally:
        elapsed = (time.time() - start_time) * 1000
        stats_service.record_request_time(elapsed)


async def _delete_package(
    cache_service: CacheServiceDep,
    stats_service: StatsServiceDep,
    name: str,
    version: str,
    sha: str,
    triplet: str,
    tag: str | None = None,
) -> dict[str, Any]:
    """Handle a DELETE request for both route shapes."""
    start_time = time.time()

    try:
        deleted = await cache_service.delete_package(name, version, sha, triplet, tag=tag)

        if deleted:
            return {
                "status": "deleted",
                "name": name,
                "version": version,
                "sha": sha,
                "triplet": triplet,
                "tag": tag,
            }
        else:
            raise HTTPException(status_code=404, detail="Package not found")

    except (InvalidTagError, TagsDisabledError) as e:
        raise _reject_bad_tag(e)
    except HTTPException:
        raise
    except StorageError as e:
        stats_service.record_error()
        if "read-only" in str(e).lower():
            raise HTTPException(status_code=403, detail="Server is in read-only mode")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        stats_service.record_error()
        logger.error(
            "Error deleting package",
            tag=tag,
            name=name,
            version=version,
            sha=sha,
            triplet=triplet,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        elapsed = (time.time() - start_time) * 1000
        stats_service.record_request_time(elapsed)


@router.head(UNTAGGED_PATH)
async def check_package(
    name: str,
    version: str,
    sha: str,
    triplet: str,
    cache_service: CacheServiceDep,
    stats_service: StatsServiceDep,
) -> Response:
    """Check whether a package exists in the untagged namespace.

    Used by vcpkg to test for a binary package before downloading it.
    """
    return await _check_package(cache_service, stats_service, name, version, sha, triplet)


@router.head(TAGGED_PATH)
async def check_tagged_package(
    tag: str,
    name: str,
    version: str,
    sha: str,
    triplet: str,
    cache_service: CacheServiceDep,
    stats_service: StatsServiceDep,
) -> Response:
    """Check whether a package exists in a build tag."""
    return await _check_package(cache_service, stats_service, name, version, sha, triplet, tag=tag)


@router.get(UNTAGGED_PATH)
async def download_package(
    name: str,
    version: str,
    sha: str,
    triplet: str,
    cache_service: CacheServiceDep,
    stats_service: StatsServiceDep,
) -> StreamingResponse:
    """Download a package from the untagged namespace."""
    return await _download_package(cache_service, stats_service, name, version, sha, triplet)


@router.get(TAGGED_PATH)
async def download_tagged_package(
    tag: str,
    name: str,
    version: str,
    sha: str,
    triplet: str,
    cache_service: CacheServiceDep,
    stats_service: StatsServiceDep,
) -> StreamingResponse:
    """Download a package from a build tag."""
    return await _download_package(
        cache_service, stats_service, name, version, sha, triplet, tag=tag
    )


@router.put(UNTAGGED_PATH)
async def upload_package(
    name: str,
    version: str,
    sha: str,
    triplet: str,
    request: Request,
    cache_service: CacheServiceDep,
    stats_service: StatsServiceDep,
) -> dict[str, Any]:
    """Upload a package into the untagged namespace."""
    return await _upload_package(request, cache_service, stats_service, name, version, sha, triplet)


@router.put(TAGGED_PATH)
async def upload_tagged_package(
    tag: str,
    name: str,
    version: str,
    sha: str,
    triplet: str,
    request: Request,
    cache_service: CacheServiceDep,
    stats_service: StatsServiceDep,
) -> dict[str, Any]:
    """Upload a package into a build tag.

    If the same package is already stored the bytes are not written again; the
    tag only gains a reference to them.
    """
    return await _upload_package(
        request, cache_service, stats_service, name, version, sha, triplet, tag=tag
    )


@router.delete(UNTAGGED_PATH)
async def delete_package(
    name: str,
    version: str,
    sha: str,
    triplet: str,
    cache_service: CacheServiceDep,
    stats_service: StatsServiceDep,
) -> dict[str, Any]:
    """Delete a package from the untagged namespace."""
    return await _delete_package(cache_service, stats_service, name, version, sha, triplet)


@router.delete(TAGGED_PATH)
async def delete_tagged_package(
    tag: str,
    name: str,
    version: str,
    sha: str,
    triplet: str,
    cache_service: CacheServiceDep,
    stats_service: StatsServiceDep,
) -> dict[str, Any]:
    """Delete a package from a build tag.

    Other tags referencing the same package keep working; the stored bytes are
    removed once the last reference is gone.
    """
    return await _delete_package(cache_service, stats_service, name, version, sha, triplet, tag=tag)
