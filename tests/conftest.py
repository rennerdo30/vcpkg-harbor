"""Pytest fixtures for vcpkg-harbor tests."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vcpkg_harbor.app import create_app
from vcpkg_harbor.core.config import Settings


@pytest.fixture
def settings() -> Settings:
    """Create test settings with filesystem backend."""
    return Settings(
        server={"host": "127.0.0.1", "port": 15151},
        storage={"type": "filesystem", "path": "/tmp/vcpkg-harbor-test"},
        logging={"level": "DEBUG", "file": None},
        dashboard={"enabled": True},
        metrics={"enabled": True},
        auth={"enabled": False},
    )


@pytest.fixture
def app(settings: Settings):
    """Create test FastAPI application."""
    return create_app(settings)


@pytest.fixture
def client(app) -> TestClient:
    """Create test client with lifespan context."""
    # Clean up test directory before tests
    import shutil
    from pathlib import Path

    test_path = Path("/tmp/vcpkg-harbor-test")
    if test_path.exists():
        shutil.rmtree(test_path)
    test_path.mkdir(parents=True, exist_ok=True)

    # Use context manager to trigger lifespan events
    with TestClient(app) as client:
        yield client

    # Clean up after tests
    if test_path.exists():
        shutil.rmtree(test_path)


@pytest.fixture
def storage_path(tmp_path) -> Path:
    """Isolated filesystem storage root for a single test."""
    path = tmp_path / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def make_client(storage_path):
    """Factory building a test client with custom build tag settings.

    Usage::

        with make_client(dedupe=False) as client:
            ...
    """

    @contextmanager
    def factory(**tag_settings: object) -> Iterator[TestClient]:
        settings = Settings(
            server={"host": "127.0.0.1", "port": 15151},
            storage={"type": "filesystem", "path": str(storage_path)},
            logging={"level": "DEBUG", "file": None},
            dashboard={"enabled": True},
            metrics={"enabled": True},
            auth={"enabled": False},
            tags=tag_settings,
        )
        with TestClient(create_app(settings)) as client:
            yield client

    return factory
