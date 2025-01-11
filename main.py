from fastapi import FastAPI, HTTPException, UploadFile, Request
import logging
import logging.handlers
import os
from datetime import datetime
from fastapi.responses import StreamingResponse
from pydantic_settings import BaseSettings
from minio import Minio
from typing import Optional
from io import BytesIO
import uvicorn

class Settings(BaseSettings):
    # Server settings
    VCPKG_HOST: str = "0.0.0.0"
    VCPKG_PORT: int = 15151
    VCPKG_WORKERS: int = 4
    VCPKG_READ_ONLY: bool = False
    VCPKG_WRITE_ONLY: bool = False

    # Storage settings
    VCPKG_STORAGE_TYPE: str = "minio"  # 'minio' or 'file'
    VCPKG_STORAGE_PATH: str = "./cache"  # Used when storage_type is 'file'
    
    # MinIO settings
    VCPKG_MINIO_ENDPOINT: str = "localhost:9000"
    VCPKG_MINIO_ACCESS_KEY: str = "minioadmin"
    VCPKG_MINIO_SECRET_KEY: str = "minioadmin"
    VCPKG_MINIO_BUCKET: str = "vcpkg-harbor"
    VCPKG_MINIO_SECURE: bool = False

    # Logging settings
    VCPKG_LOG_LEVEL: str = "INFO"
    VCPKG_LOG_JSON: bool = False
    VCPKG_LOG_FILE: str = "logs/vcpkg-harbor.log"
    VCPKG_LOG_RETENTION_DAYS: int = 30

    class Config:
        env_file = ".env"
        case_sensitive = True  # Ensure environment variables are case-sensitive

    @property
    def log_level(self) -> int:
        """Convert string log level to logging constant"""
        return getattr(logging, self.VCPKG_LOG_LEVEL.upper())

def setup_logging(settings: Settings):
    """Configure logging based on settings"""
    # Create logs directory if it doesn't exist
    os.makedirs(os.path.dirname(settings.VCPKG_LOG_FILE), exist_ok=True)
    
    # Create logger
    logger = logging.getLogger("vcpkg-harbor")
    logger.setLevel(settings.log_level)
    
    # Determine formatter based on settings
    if settings.VCPKG_LOG_JSON:
        formatter = logging.Formatter(
            '{"timestamp":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}'
        )
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'
        )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(settings.log_level)
    console_handler.setFormatter(formatter)
    
    # File handler with TimedRotatingFileHandler
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=settings.VCPKG_LOG_FILE,
        when='midnight',
        interval=1,
        backupCount=settings.VCPKG_LOG_RETENTION_DAYS
    )
    file_handler.setLevel(settings.log_level)
    file_handler.setFormatter(formatter)
    
    # Remove any existing handlers
    logger.handlers.clear()
    
    # Add handlers to logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger

# Initialize settings and logger
settings = Settings()
logger = setup_logging(settings)
app = FastAPI(title="vcpkg-harbor")

# Initialize MinIO client
minio_client = Minio(
    settings.VCPKG_MINIO_ENDPOINT,
    access_key=settings.VCPKG_MINIO_ACCESS_KEY,
    secret_key=settings.VCPKG_MINIO_SECRET_KEY,
    secure=settings.VCPKG_MINIO_SECURE
)

# Ensure bucket exists
if not minio_client.bucket_exists(settings.VCPKG_MINIO_BUCKET):
    minio_client.make_bucket(settings.VCPKG_MINIO_BUCKET)

def get_object_path(name: str, version: str, sha: str) -> str:
    """Generate MinIO object path from package details"""
    return f"{name}/{version}/{sha}"

@app.head("/{name}/{version}/{sha}")
async def check_package(name: str, version: str, sha: str):
    """Check if a package exists in the cache"""
    try:
        minio_client.stat_object(
            settings.VCPKG_MINIO_BUCKET,
            get_object_path(name, version, sha)
        )
        logger.info(f"Package check: {name}/{version}/{sha} exists")
        return {"status": "exists"}
    except:
        logger.warning(f"Package check: {name}/{version}/{sha} not found")
        raise HTTPException(status_code=404, detail="Package not found")

@app.get("/{name}/{version}/{sha}")
async def download_package(name: str, version: str, sha: str):
    """Download a package from the cache"""
    logger.info(f"Download request: {name}/{version}/{sha}")
    try:
        response = minio_client.get_object(
            settings.VCPKG_MINIO_BUCKET,
            get_object_path(name, version, sha)
        )
        return StreamingResponse(
            response.stream(),
            media_type="application/octet-stream",
            headers={
                "Content-Length": str(response.getheaders().get("Content-Length", 0))
            }
        )
    except Exception as e:
        logger.error(f"Download failed: {name}/{version}/{sha} - {str(e)}")
        raise HTTPException(status_code=404, detail="Package not found")

@app.put("/{name}/{version}/{sha}")
async def upload_package(name: str, version: str, sha: str, request: Request):
    """Upload a package to the cache"""
    logger.info(f"Upload request: {name}/{version}/{sha}")
    object_path = get_object_path(name, version, sha)
    
    # Check if package already exists
    try:
        minio_client.stat_object(settings.VCPKG_MINIO_BUCKET, object_path)
        logger.warning(f"Upload conflict: {name}/{version}/{sha} already exists")
        raise HTTPException(status_code=409, detail="Package already exists")
    except Exception as e:
        if "NoSuchKey" not in str(e):
            logger.error(f"Error checking existence: {name}/{version}/{sha} - {str(e)}")
            raise HTTPException(status_code=500, detail="Error checking package existence")

    try:
        # Stream the upload to MinIO
        body = await request.body()
        data = BytesIO(body)
        result = minio_client.put_object(
            bucket_name=settings.VCPKG_MINIO_BUCKET,
            object_name=object_path,
            data=data,
            length=len(body),
            content_type="application/octet-stream"
        )
        logger.info(f"Upload successful: {name}/{version}/{sha} (size: {len(body)} bytes)")
        return {
            "status": "success",
            "size": len(body),
            "etag": result.etag if hasattr(result, 'etag') else None
        }
    except Exception as e:
        logger.error(f"Upload failed: {name}/{version}/{sha} - {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@app.on_event("startup")
async def startup_event():
    """Startup event handler"""
    logger.info(f"Starting vcpkg-harbor on {settings.VCPKG_HOST}:{settings.VCPKG_PORT}")
    logger.info(f"Connected to MinIO at {settings.VCPKG_MINIO_ENDPOINT}")
    logger.info(f"Using bucket: {settings.VCPKG_MINIO_BUCKET}")
    if settings.VCPKG_READ_ONLY:
        logger.info("Server running in READ-ONLY mode")
    if settings.VCPKG_WRITE_ONLY:
        logger.info("Server running in WRITE-ONLY mode")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.VCPKG_HOST,
        port=settings.VCPKG_PORT,
        reload=True,
        workers=settings.VCPKG_WORKERS
    )