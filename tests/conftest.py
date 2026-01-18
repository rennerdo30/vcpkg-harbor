"""Pytest fixtures for vcpkg-harbor tests."""

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
    """Create test client."""
    return TestClient(app)
