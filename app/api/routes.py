import os
import time
from typing import Optional
from datetime import datetime

import structlog
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.storage.base import (
    PackageIdentifier,  # Changed from PackageInfo
    NotFoundError,
    AlreadyExistsError,
    StorageError
)
from .models import (
    HealthResponse,
    MetricsResponse,
    UploadResponse,
    ErrorResponse
)

# Initialize router
router = APIRouter()

# Initialize logger
logger = structlog.get_logger(__name__)

# Track server start time
START_TIME = time.time()

@router.get("/", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        storage_type=settings.storage_type,
        timestamp=datetime.utcnow()
    )

@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics():
    """Get server metrics."""
    from app import storage_backend
    
    uptime = time.time() - START_TIME
    
    # Get storage stats if available
    total_packages = 0
    total_size = 0
    storage_stats = {}
    
    return MetricsResponse(
        status="available",
        storage_type=settings.storage_type,
        uptime_seconds=uptime,
        total_packages=total_packages,
        total_size_bytes=total_size,
        storage_stats=storage_stats,
        timestamp=datetime.utcnow()
    )

@router.head("/{name}/{version}/{sha}")
async def check_package(
    name: str,
    version: str,
    sha: str,
    request: Request
) -> Response:
    """Check if package exists."""
    from app import storage_backend
    
    if settings.server.write_only:
        raise HTTPException(status_code=405, detail="Server is in write-only mode")
    
    package = PackageIdentifier(name=name, version=version, sha=sha)
    logger.debug("check_package", package=str(package))
    
    try:
        size = await storage_backend.get_size(package)
        return Response(headers={"Content-Length": str(size)})
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Package not found")
    except StorageError as e:
        logger.error("check_package_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{name}/{version}/{sha}")
async def download_package(
    name: str,
    version: str,
    sha: str,
    request: Request
) -> StreamingResponse:
    """Download a package."""
    from app.storage.backend import StorageBackend as storage_backend
    
    if settings.server.write_only:
        raise HTTPException(status_code=405, detail="Server is in write-only mode")
    
    package = PackageIdentifier(name=name, version=version, sha=sha)
    logger.debug("download_package", package=str(package))
    
    async def stream_package():
        read_pipe, write_pipe = os.pipe()
        read_pipe = os.fdopen(read_pipe, 'rb')
        write_pipe = os.fdopen(write_pipe, 'wb')
        
        try:
            await storage_backend.get(package, write_pipe)
            write_pipe.close()
            while chunk := read_pipe.read(8192):
                yield chunk
        except Exception as e:
            logger.error("download_failed", error=str(e))
            raise
        finally:
            read_pipe.close()
    
    try:
        return StreamingResponse(
            stream_package(),
            media_type='application/octet-stream',
            headers={
                'Content-Disposition': f'attachment; filename={sha}.bin'
            }
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Package not found")
    except StorageError as e:
        logger.error("download_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{name}/{version}/{sha}", response_model=UploadResponse)
async def upload_package(
    name: str,
    version: str,
    sha: str,
    request: Request
) -> UploadResponse:
    """Upload a package."""
    from app import storage_backend
    
    if settings.server.read_only:
        raise HTTPException(status_code=405, detail="Server is in read-only mode")
    
    package = PackageIdentifier(name=name, version=version, sha=sha)
    logger.debug("upload_package", package=str(package))
    
    try:
        # Check if package already exists before starting upload
        if await storage_backend.exists(package):
            logger.warning("package_already_exists", package=str(package))
            raise HTTPException(status_code=409, detail="Package already exists")
        
        # Stream the upload
        size = await storage_backend.put(package, request.stream())
        
        logger.info("upload_successful", package=str(package), size=size)
        return UploadResponse(
            status="success",
            message="Package uploaded successfully",
            size_bytes=size,
            timestamp=datetime.utcnow()
        )
        
    except AlreadyExistsError:
        raise HTTPException(status_code=409, detail="Package already exists")
    except StorageError as e:
        logger.error("upload_failed", package=str(package), error=str(e))
        raise HTTPException(status_code=500, detail=str(e))