from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str = Field(..., example="healthy")
    version: str = Field(..., example="1.0.0")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    storage_type: str = Field(..., example="file")


class MetricsResponse(BaseModel):
    """Metrics response model."""
    status: str = Field(..., example="available")
    storage_type: str = Field(..., example="file")
    uptime_seconds: float = Field(..., example=3600)
    total_packages: int = Field(..., example=100)
    total_size_bytes: int = Field(..., example=1024000)
    storage_stats: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ErrorResponse(BaseModel):
    """Error response model."""
    detail: str = Field(..., example="Package not found")
    error_code: Optional[str] = Field(None, example="NOT_FOUND")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class UploadResponse(BaseModel):
    """Upload success response model."""
    status: str = Field(..., example="success")
    message: str = Field(..., example="Package uploaded successfully")
    size_bytes: int = Field(..., example=1024000)
    timestamp: datetime = Field(default_factory=datetime.utcnow)