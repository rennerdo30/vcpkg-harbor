"""Tests that every storage backend implements the shared interface and layout.

These tests never touch the network: the object store backends create their
clients lazily, so key construction and protocol conformance can be checked
without a live service.
"""

import pytest

from vcpkg_harbor.storage.backends.azure import AzureBackend
from vcpkg_harbor.storage.backends.filesystem import FilesystemBackend
from vcpkg_harbor.storage.backends.gcs import GCSBackend
from vcpkg_harbor.storage.backends.minio import MinioBackend
from vcpkg_harbor.storage.backends.s3 import S3Backend
from vcpkg_harbor.storage.base import StorageBackend
from vcpkg_harbor.storage.layout import PackageKey, tag_object_scope

KEY = PackageKey("zlib", "1.3.1", "abc123", "x64-linux")

# Each backend names its key builder differently.
BACKENDS = [
    (MinioBackend, "_get_object_path"),
    (S3Backend, "_get_object_key"),
    (AzureBackend, "_get_blob_name"),
    (GCSBackend, "_get_blob_name"),
]


@pytest.fixture
def backends(tmp_path):
    """One instance of every backend, including the filesystem one."""
    return [
        FilesystemBackend(path=str(tmp_path)),
        MinioBackend(),
        S3Backend(),
        AzureBackend(),
        GCSBackend(),
    ]


def test_all_backends_satisfy_the_protocol(backends):
    """Every backend implements the full StorageBackend protocol."""
    for backend in backends:
        assert isinstance(backend, StorageBackend), type(backend).__name__


@pytest.mark.parametrize(
    "required", ["put_metadata", "get_metadata", "delete_metadata", "list_metadata"]
)
def test_all_backends_implement_the_metadata_api(backends, required):
    """The build tag index needs the metadata API on every backend."""
    for backend in backends:
        assert callable(getattr(backend, required, None)), type(backend).__name__


@pytest.mark.parametrize(("backend_class", "builder"), BACKENDS)
def test_object_store_keys_use_the_shared_layout(backend_class, builder):
    """Unscoped keys are the identity key, scoped keys carry the tag prefix."""
    build = getattr(backend_class(), builder)

    assert build(KEY.name, KEY.version, KEY.sha, KEY.triplet) == "zlib/1.3.1/abc123/x64-linux"
    assert (
        build(KEY.name, KEY.version, KEY.sha, KEY.triplet, tag_object_scope("nightly"))
        == "_harbor/objects/nightly/zlib/1.3.1/abc123/x64-linux"
    )


def test_filesystem_keys_use_the_shared_layout(tmp_path):
    """The filesystem backend maps the same keys onto paths below its root."""
    backend = FilesystemBackend(path=str(tmp_path))

    unscoped = backend._get_package_path(KEY.name, KEY.version, KEY.sha, KEY.triplet)
    assert unscoped == tmp_path.resolve() / "zlib/1.3.1/abc123/x64-linux"

    scoped = backend._get_package_path(
        KEY.name, KEY.version, KEY.sha, KEY.triplet, tag_object_scope("nightly")
    )
    assert scoped == tmp_path.resolve() / "_harbor/objects/nightly/zlib/1.3.1/abc123/x64-linux"
