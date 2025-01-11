from contextlib import asynccontextmanager
import sys
from pathlib import Path

import structlog
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging  # Changed from configure_logging
from app.api.routes import router
from app.storage.base import StorageError
from app.storage.file import FileStorageBackend
from app.storage.minio import MinioStorageBackend

# Initialize logger
logger = structlog.get_logger(__name__)

# Global storage instance
storage_backend = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI application."""
    global storage_backend

    # Configure logging
    setup_logging(
        level=settings.logging.level,
        json_format=settings.logging.json_format,
        log_file=settings.logging.file
    )

    logger.info(
        "starting_application",
        version="1.0.0",
        storage_type=settings.storage_type,
        host=settings.server.host,
        port=settings.server.port
    )

    try:
        # Initialize storage backend
        if settings.storage_type == "file":
            storage_path = Path(settings.file_storage.path)
            storage_path.mkdir(parents=True, exist_ok=True)
            storage_backend = FileStorageBackend(storage_path)
            logger.info("initialized_file_storage", path=str(storage_path))

        elif settings.storage_type == "minio":
            storage_backend = MinioStorageBackend(
                endpoint=settings.minio_storage.endpoint,
                access_key=settings.minio_storage.access_key,
                secret_key=settings.minio_storage.secret_key,
                bucket=settings.minio_storage.bucket,
                region=settings.minio_storage.region,
                secure=settings.minio_storage.secure
            )
            logger.info(
                "initialized_minio_storage",
                endpoint=settings.minio_storage.endpoint,
                bucket=settings.minio_storage.bucket
            )

        else:
            raise ValueError(f"Unsupported storage type: {settings.storage_type}")

        await storage_backend.initialize()
        yield

    except Exception as e:
        logger.error("startup_failed", error=str(e))
        sys.exit(1)

    finally:
        # Cleanup
        if storage_backend:
            try:
                await storage_backend.cleanup()
                logger.info("storage_cleanup_complete")
            except Exception as e:
                logger.error("storage_cleanup_failed", error=str(e))

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="vcpkg-harbor",
        description="A high-performance binary cache server for vcpkg",
        version="1.0.0",
        lifespan=lifespan
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add global error handler
    @app.exception_handler(StorageError)
    async def storage_error_handler(request: Request, exc: StorageError):
        logger.error(
            "storage_error",
            error=str(exc),
            path=request.url.path,
            method=request.method
        )
        return JSONResponse(
            status_code=500,
            content={"detail": str(exc)}
        )

    # Add request logging middleware
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        logger.info(
            "request_started",
            path=request.url.path,
            method=request.method,
            client=request.client.host if request.client else None
        )
        response = await call_next(request)
        logger.info(
            "request_completed",
            path=request.url.path,
            method=request.method,
            status_code=response.status_code
        )
        return response

    # Include routers
    app.include_router(router)

    return app

# Create the FastAPI application instance
app = create_app()

def main():
    """Main entry point."""
    try:
        uvicorn.run(
            app,
            host=settings.server.host,
            port=settings.server.port,
            log_level=settings.logging.level.lower(),
            proxy_headers=True,
            forwarded_allow_ips="*",
            workers=settings.server.workers
        )
    except Exception as e:
        logger.error("application_error", error=str(e))
        sys.exit(1)

if __name__ == "__main__":
    main()