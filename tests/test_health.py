"""Tests for health endpoints."""

import pytest
from fastapi.testclient import TestClient


def test_health_endpoint(client: TestClient):
    """Test basic health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "version" in data


def test_liveness_endpoint(client: TestClient):
    """Test liveness endpoint."""
    response = client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"


def test_readiness_endpoint(client: TestClient):
    """Test readiness endpoint."""
    response = client.get("/health/ready")
    # May return 200 or 503 depending on storage state
    assert response.status_code in (200, 503)


def test_health_details_endpoint(client: TestClient):
    """Test detailed health endpoint."""
    response = client.get("/health/details")
    assert response.status_code == 200
    data = response.json()
    assert "storage" in data
    assert "cache" in data
    assert "requests" in data
