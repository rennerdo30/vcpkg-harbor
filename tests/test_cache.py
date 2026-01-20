"""Tests for cache API endpoints."""

import pytest
from fastapi.testclient import TestClient


def test_check_nonexistent_package(client: TestClient):
    """Test HEAD request for nonexistent package."""
    response = client.head("/test-package/1.0.0/abc123/x64-linux")
    assert response.status_code == 404


def test_download_nonexistent_package(client: TestClient):
    """Test GET request for nonexistent package."""
    response = client.get("/test-package/1.0.0/abc123/x64-linux")
    assert response.status_code == 404


def test_upload_and_download_package(client: TestClient):
    """Test uploading and downloading a package."""
    test_data = b"test package content"

    # Upload
    response = client.put(
        "/test-package/1.0.0/sha256abc/x64-linux",
        content=test_data,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["size"] == len(test_data)
    assert data["triplet"] == "x64-linux"

    # Check exists
    response = client.head("/test-package/1.0.0/sha256abc/x64-linux")
    assert response.status_code == 200

    # Download
    response = client.get("/test-package/1.0.0/sha256abc/x64-linux")
    assert response.status_code == 200
    assert response.content == test_data


def test_upload_duplicate_package(client: TestClient):
    """Test uploading a package that already exists."""
    test_data = b"test package content"

    # First upload
    response = client.put(
        "/test-package2/1.0.0/sha256def/x64-linux",
        content=test_data,
    )
    assert response.status_code == 200

    # Second upload should fail with 409
    response = client.put(
        "/test-package2/1.0.0/sha256def/x64-linux",
        content=test_data,
    )
    assert response.status_code == 409


def test_delete_package(client: TestClient):
    """Test deleting a package."""
    test_data = b"test package content"

    # Upload
    response = client.put(
        "/test-package3/1.0.0/sha256ghi/x64-linux",
        content=test_data,
    )
    assert response.status_code == 200

    # Delete
    response = client.delete("/test-package3/1.0.0/sha256ghi/x64-linux")
    assert response.status_code == 200

    # Verify deleted
    response = client.head("/test-package3/1.0.0/sha256ghi/x64-linux")
    assert response.status_code == 404


def test_different_triplets(client: TestClient):
    """Test that same package with different triplets are stored separately."""
    test_data_linux = b"linux package content"
    test_data_windows = b"windows package content"

    # Upload for x64-linux
    response = client.put(
        "/test-package4/1.0.0/sha256jkl/x64-linux",
        content=test_data_linux,
    )
    assert response.status_code == 200

    # Upload for x64-windows (same name/version/sha, different triplet)
    response = client.put(
        "/test-package4/1.0.0/sha256jkl/x64-windows",
        content=test_data_windows,
    )
    assert response.status_code == 200

    # Download linux version
    response = client.get("/test-package4/1.0.0/sha256jkl/x64-linux")
    assert response.status_code == 200
    assert response.content == test_data_linux

    # Download windows version
    response = client.get("/test-package4/1.0.0/sha256jkl/x64-windows")
    assert response.status_code == 200
    assert response.content == test_data_windows
