import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from app.storage.base import PackageIdentifier

# Health check and metrics tests
def test_health_check(test_client: TestClient):
    """Test health check endpoint."""
    response = test_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data
    assert "timestamp" in data
    assert "storage_type" in data

def test_metrics(test_client: TestClient):
    """Test metrics endpoint."""
    response = test_client.get("/metrics")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "available"
    assert "uptime_seconds" in data
    assert "total_packages" in data
    assert isinstance(data["total_packages"], int)
    assert "storage_stats" in data
    assert isinstance(data["storage_stats"], dict)

# Package operation tests
@pytest.mark.parametrize("storage_backend", ["file", "minio"], indirect=True)
class TestPackageOperations:
    """Test package operations with different storage backends."""

    def test_package_upload_download_cycle(
        self,
        test_client: TestClient,
        sample_package: PackageIdentifier,
        sample_data: bytes
    ):
        """Test complete package upload and download cycle."""
        # Upload package
        response = test_client.put(
            f"/{sample_package.name}/{sample_package.version}/{sample_package.sha}",
            content=sample_data
        )
        assert response.status_code == 200
        upload_data = response.json()
        assert upload_data["status"] == "success"
        assert upload_data["size_bytes"] == len(sample_data)

        # Check existence
        response = test_client.head(
            f"/{sample_package.name}/{sample_package.version}/{sample_package.sha}"
        )
        assert response.status_code == 200
        assert int(response.headers["Content-Length"]) == len(sample_data)

        # Download package
        response = test_client.get(
            f"/{sample_package.name}/{sample_package.version}/{sample_package.sha}"
        )
        assert response.status_code == 200
        assert response.content == sample_data

    def test_upload_duplicate_package(
        self,
        test_client: TestClient,
        sample_package: PackageIdentifier,
        sample_data: bytes
    ):
        """Test uploading the same package twice."""
        # First upload
        response = test_client.put(
            f"/{sample_package.name}/{sample_package.version}/{sample_package.sha}",
            content=sample_data
        )
        assert response.status_code == 200

        # Second upload should fail
        response = test_client.put(
            f"/{sample_package.name}/{sample_package.version}/{sample_package.sha}",
            content=sample_data
        )
        assert response.status_code == 409  # Conflict

    def test_download_nonexistent_package(
        self,
        test_client: TestClient,
        sample_package: PackageIdentifier
    ):
        """Test downloading a package that doesn't exist."""
        response = test_client.get(
            f"/{sample_package.name}/{sample_package.version}/{sample_package.sha}"
        )
        assert response.status_code == 404

    def test_check_nonexistent_package(
        self,
        test_client: TestClient,
        sample_package: PackageIdentifier
    ):
        """Test checking a package that doesn't exist."""
        response = test_client.head(
            f"/{sample_package.name}/{sample_package.version}/{sample_package.sha}"
        )
        assert response.status_code == 404

    @pytest.mark.parametrize("chunk_size", [1024, 8192, 16384])
    def test_large_package_upload(
        self,
        test_client: TestClient,
        sample_package: PackageIdentifier,
        chunk_size: int,
        tmp_path: Path
    ):
        """Test uploading large packages with different chunk sizes."""
        # Create large test data
        large_data = os.urandom(chunk_size * 10)  # 10 chunks of data
        
        # Upload in chunks
        response = test_client.put(
            f"/{sample_package.name}/{sample_package.version}/{sample_package.sha}",
            content=large_data
        )
        assert response.status_code == 200
        
        # Verify download
        response = test_client.get(
            f"/{sample_package.name}/{sample_package.version}/{sample_package.sha}"
        )
        assert response.status_code == 200
        assert response.content == large_data

    def test_invalid_package_names(self, test_client: TestClient):
        """Test handling of invalid package names."""
        invalid_names = [
            "",  # Empty name
            "../malicious",  # Path traversal attempt
            "space name",  # Space in name
            "special#chars",  # Special characters
            "a" * 256,  # Too long
        ]

        for name in invalid_names:
            response = test_client.put(
                f"/{name}/1.0.0/abcdef123456",
                content=b"test data"
            )
            assert response.status_code in (400, 422)  # Bad request or validation error

    def test_concurrent_uploads(
        self,
        test_client: TestClient,
        sample_data: bytes
    ):
        """Test concurrent uploads of different packages."""
        import asyncio
        import httpx

        async def upload_package(name: str) -> httpx.Response:
            async with httpx.AsyncClient(base_url=test_client.base_url) as client:
                return await client.put(
                    f"/{name}/1.0.0/abcdef123456",
                    content=sample_data
                )

        # Upload multiple packages concurrently
        package_names = [f"package-{i}" for i in range(5)]
        
        async def run_concurrent_uploads():
            tasks = [upload_package(name) for name in package_names]
            responses = await asyncio.gather(*tasks)
            return responses

        responses = asyncio.run(run_concurrent_uploads())
        
        # Verify all uploads succeeded
        for response in responses:
            assert response.status_code == 200

    @pytest.mark.parametrize("read_only", [True, False])
    def test_read_only_mode(
        self,
        test_client: TestClient,
        sample_package: PackageIdentifier,
        sample_data: bytes,
        test_settings,
        read_only: bool
    ):
        """Test read-only mode behavior."""
        # Upload package first
        if not read_only:
            response = test_client.put(
                f"/{sample_package.name}/{sample_package.version}/{sample_package.sha}",
                content=sample_data
            )
            assert response.status_code == 200

        # Enable read-only mode
        test_settings.server.read_only = read_only

        # Try upload in read-only mode
        response = test_client.put(
            f"/{sample_package.name}/{sample_package.version}/{sample_package.sha}",
            content=sample_data
        )
        assert response.status_code == 405 if read_only else 200

    @pytest.mark.parametrize("write_only", [True, False])
    def test_write_only_mode(
        self,
        test_client: TestClient,
        sample_package: PackageIdentifier,
        sample_data: bytes,
        test_settings,
        write_only: bool
    ):
        """Test write-only mode behavior."""
        # Upload package
        response = test_client.put(
            f"/{sample_package.name}/{sample_package.version}/{sample_package.sha}",
            content=sample_data
        )
        assert response.status_code == 200

        # Enable write-only mode
        test_settings.server.write_only = write_only

        # Try download in write-only mode
        response = test_client.get(
            f"/{sample_package.name}/{sample_package.version}/{sample_package.sha}"
        )
        assert response.status_code == 405 if write_only else 200

# Special case tests
def test_malformed_requests(test_client: TestClient):
    """Test handling of malformed requests."""
    test_cases = [
        # Missing version
        ("/package//sha", b"test"),
        # Missing hash
        ("/package/1.0.0/", b"test"),
        # Invalid URL encoding
        ("/package%20name/1.0.0/sha", b"test"),
        # Too many path segments
        ("/extra/package/1.0.0/sha", b"test"),
    ]

    for path, data in test_cases:
        response = test_client.put(path, content=data)
        assert response.status_code in (400, 404, 422)

def test_error_responses(test_client: TestClient):
    """Test error response format."""
    # Try to download non-existent package
    response = test_client.get("/nonexistent/1.0.0/sha")
    assert response.status_code == 404
    error_data = response.json()
    assert "detail" in error_data
    assert "timestamp" in error_data

def test_content_type_handling(
    test_client: TestClient,
    sample_package: PackageIdentifier,
    sample_data: bytes
):
    """Test content type handling."""
    # Upload with custom content type
    headers = {"Content-Type": "application/octet-stream"}
    response = test_client.put(
        f"/{sample_package.name}/{sample_package.version}/{sample_package.sha}",
        content=sample_data,
        headers=headers
    )
    assert response.status_code == 200

    # Verify content type on download
    response = test_client.get(
        f"/{sample_package.name}/{sample_package.version}/{sample_package.sha}"
    )
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/octet-stream"

def test_package_listing(test_client: TestClient):
    """Test package listing endpoints if supported."""
    # Upload some test packages
    packages = [
        ("pkg1", "1.0.0", "sha1"),
        ("pkg1", "1.0.1", "sha2"),
        ("pkg2", "2.0.0", "sha3"),
    ]

    for name, version, sha in packages:
        response = test_client.put(
            f"/{name}/{version}/{sha}",
            content=b"test data"
        )
        assert response.status_code == 200

    # Test listing all versions of a package
    response = test_client.get("/pkg1")
    if response.status_code != 405:  # If listing is supported
        assert response.status_code == 200
        data = response.json()
        assert len(data["versions"]) == 2
        assert "1.0.0" in data["versions"]
        assert "1.0.1" in data["versions"]

    # Test listing packages for a specific version
    response = test_client.get("/pkg1/1.0.0")
    if response.status_code != 405:  # If listing is supported
        assert response.status_code == 200
        data = response.json()
        assert len(data["packages"]) == 1
        assert data["packages"][0]["sha"] == "sha1"