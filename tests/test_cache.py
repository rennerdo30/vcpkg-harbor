"""Tests for cache API endpoints."""

import pytest
from fastapi.testclient import TestClient


def test_check_nonexistent_package(client: TestClient):
    """Test HEAD request for nonexistent package."""
    response = client.head("/test-package/1.0.0/abc123")
    assert response.status_code == 404


def test_download_nonexistent_package(client: TestClient):
    """Test GET request for nonexistent package."""
    response = client.get("/test-package/1.0.0/abc123")
    assert response.status_code == 404


def test_upload_and_download_package(client: TestClient):
    """Test uploading and downloading a package."""
    test_data = b"test package content"

    # Upload
    response = client.put(
        "/test-package/1.0.0/sha256abc",
        content=test_data,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["size"] == len(test_data)

    # Check exists
    response = client.head("/test-package/1.0.0/sha256abc")
    assert response.status_code == 200

    # Download
    response = client.get("/test-package/1.0.0/sha256abc")
    assert response.status_code == 200
    assert response.content == test_data


def test_upload_duplicate_package(client: TestClient):
    """Test uploading a package that already exists."""
    test_data = b"test package content"

    # First upload
    response = client.put(
        "/test-package2/1.0.0/sha256def",
        content=test_data,
    )
    assert response.status_code == 200

    # Second upload should fail with 409
    response = client.put(
        "/test-package2/1.0.0/sha256def",
        content=test_data,
    )
    assert response.status_code == 409


def test_delete_package(client: TestClient):
    """Test deleting a package."""
    test_data = b"test package content"

    # Upload
    response = client.put(
        "/test-package3/1.0.0/sha256ghi",
        content=test_data,
    )
    assert response.status_code == 200

    # Delete
    response = client.delete("/test-package3/1.0.0/sha256ghi")
    assert response.status_code == 200

    # Verify deleted
    response = client.head("/test-package3/1.0.0/sha256ghi")
    assert response.status_code == 404
