# Testing

vcpkg-harbor uses pytest for testing.

## Running Tests

```bash
# Run all tests
./scripts/test.sh

# Run specific file
pytest tests/test_health.py -v

# Run specific test
pytest tests/test_cache.py::test_upload_and_download_package -v

# Run with coverage
pytest tests/ --cov=vcpkg_harbor --cov-report=html
```

## Test Structure

```
tests/
├── __init__.py
├── conftest.py           # Shared fixtures
├── test_config.py        # Configuration tests
├── test_health.py        # Health endpoint tests
├── test_cache.py         # Cache API tests
└── test_storage/         # Storage backend tests
    ├── test_filesystem.py
    └── test_minio.py
```

## Fixtures

### Application Fixture

```python
@pytest.fixture
def app(settings: Settings):
    """Create test FastAPI application."""
    return create_app(settings)

@pytest.fixture
def client(app) -> TestClient:
    """Create test client."""
    return TestClient(app)
```

### Settings Fixture

```python
@pytest.fixture
def settings() -> Settings:
    """Create test settings with filesystem backend."""
    return Settings(
        storage={"type": "filesystem", "path": "/tmp/test"},
        logging={"level": "DEBUG", "file": None},
    )
```

## Writing Tests

### Testing Endpoints

```python
def test_health_endpoint(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
```

### Testing Storage Backends

```python
@pytest.mark.asyncio
async def test_filesystem_put_get():
    backend = FilesystemBackend(path="/tmp/test")
    await backend.initialize()

    # Upload
    data = async_iter([b"test data"])
    info = await backend.put("pkg", "1.0", "sha", data)
    assert info.size > 0

    # Download
    chunks = []
    async for chunk in backend.get("pkg", "1.0", "sha"):
        chunks.append(chunk)
    assert b"".join(chunks) == b"test data"
```

## Integration Tests

For testing with real services (MinIO), use Docker:

```python
@pytest.fixture(scope="session")
def minio_container():
    """Start MinIO container for integration tests."""
    # Uses testcontainers or docker-compose
```

## CI Testing

GitHub Actions runs tests on every PR:

```yaml
- name: Run tests
  env:
    VCPKG_STORAGE_TYPE: filesystem
  run: pytest tests/ -v --cov=vcpkg_harbor
```

## Coverage

View coverage report:

```bash
# Generate HTML report
pytest tests/ --cov=vcpkg_harbor --cov-report=html

# Open report
open htmlcov/index.html
```

Coverage is uploaded to Codecov on CI.
