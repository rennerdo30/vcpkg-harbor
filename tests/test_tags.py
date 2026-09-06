"""Tests for build tags, deduplication and reference counting."""

import json
from pathlib import Path

from vcpkg_harbor.api.cache import TAGGED_PATH, UNTAGGED_PATH
from vcpkg_harbor.core.config import DEFAULT_NAMESPACE
from vcpkg_harbor.storage.layout import OBJECTS_PREFIX, REFS_PREFIX, TAGS_PREFIX

IDENTITY = "zlib/1.3.1/abc123/x64-linux"
PAYLOAD = b"zlib binary package payload"


def identity_blob(storage_path: Path, identity: str = IDENTITY) -> Path:
    """Path of the shared (deduplicated) object for a package identity."""
    return storage_path / identity


def scoped_blob(storage_path: Path, tag: str, identity: str = IDENTITY) -> Path:
    """Path of a tag private object copy."""
    return storage_path / OBJECTS_PREFIX / tag / identity


def refs_document(storage_path: Path, identity: str = IDENTITY) -> dict:
    """Read the reference counter document of a package identity."""
    path = storage_path / REFS_PREFIX / f"{identity}.json"
    return json.loads(path.read_text())


def tag_entry(storage_path: Path, tag: str, identity: str = IDENTITY) -> Path:
    """Path of a tag membership document."""
    return storage_path / TAGS_PREFIX / tag / f"{identity}.json"


def blob_count(storage_path: Path, identity: str = IDENTITY) -> int:
    """Number of stored copies of the package payload."""
    return sum(
        1 for path in storage_path.rglob("*") if path.is_file() and path.read_bytes() == PAYLOAD
    )


# ----------------------------------------------------------------------
# Round trips
# ----------------------------------------------------------------------


def test_tagged_round_trip(make_client, storage_path):
    """PUT, HEAD, GET and DELETE all work through a tagged path."""
    with make_client() as client:
        response = client.put(f"/nightly/{IDENTITY}", content=PAYLOAD)
        assert response.status_code == 200
        body = response.json()
        assert body["tag"] == "nightly"
        assert body["namespace"] == "nightly"
        assert body["deduplicated"] is False
        assert body["size"] == len(PAYLOAD)

        assert client.head(f"/nightly/{IDENTITY}").status_code == 200

        response = client.get(f"/nightly/{IDENTITY}")
        assert response.status_code == 200
        assert response.content == PAYLOAD

        assert client.delete(f"/nightly/{IDENTITY}").status_code == 200
        assert client.head(f"/nightly/{IDENTITY}").status_code == 404
        assert not identity_blob(storage_path).exists()


def test_untagged_round_trip_keeps_legacy_layout(make_client, storage_path):
    """Untagged requests still store bytes at the historical identity key."""
    with make_client() as client:
        assert client.put(f"/{IDENTITY}", content=PAYLOAD).status_code == 200

        # Byte compatible with the pre-tag layout: cache/<name>/<version>/<sha>/<triplet>
        assert identity_blob(storage_path).read_bytes() == PAYLOAD

        body = client.put(f"/{IDENTITY}", content=PAYLOAD)
        assert body.status_code == 409

        assert client.head(f"/{IDENTITY}").status_code == 200
        assert client.get(f"/{IDENTITY}").content == PAYLOAD
        assert client.delete(f"/{IDENTITY}").status_code == 200


def test_untagged_upload_reports_default_namespace(make_client):
    """The untagged namespace is reported under its configured name."""
    with make_client() as client:
        body = client.put(f"/{IDENTITY}", content=PAYLOAD).json()
        assert body["tag"] is None
        assert body["namespace"] == DEFAULT_NAMESPACE


# ----------------------------------------------------------------------
# Isolation
# ----------------------------------------------------------------------


def test_tags_are_isolated(make_client):
    """A package uploaded to one tag is invisible to other namespaces."""
    with make_client() as client:
        assert client.put(f"/nightly/{IDENTITY}", content=PAYLOAD).status_code == 200

        assert client.head(f"/release/{IDENTITY}").status_code == 404
        assert client.get(f"/release/{IDENTITY}").status_code == 404
        assert client.head(f"/{IDENTITY}").status_code == 404
        assert client.get(f"/{IDENTITY}").status_code == 404


def test_untagged_upload_is_not_visible_to_tags(make_client):
    """The default namespace is isolated from tags too."""
    with make_client() as client:
        assert client.put(f"/{IDENTITY}", content=PAYLOAD).status_code == 200
        assert client.head(f"/nightly/{IDENTITY}").status_code == 404


def test_same_name_different_tags_hold_different_packages(make_client):
    """Two tags can hold different builds of the same port and version."""
    nightly_payload = b"nightly build"
    release_payload = b"release build"

    with make_client() as client:
        client.put("/nightly/zlib/1.3.1/nightlysha/x64-linux", content=nightly_payload)
        client.put("/release/zlib/1.3.1/releasesha/x64-linux", content=release_payload)

        assert client.get("/nightly/zlib/1.3.1/nightlysha/x64-linux").content == nightly_payload
        assert client.get("/release/zlib/1.3.1/releasesha/x64-linux").content == release_payload
        assert client.head("/nightly/zlib/1.3.1/releasesha/x64-linux").status_code == 404


# ----------------------------------------------------------------------
# Deduplication and reference counting
# ----------------------------------------------------------------------


def test_dedupe_stores_one_copy_for_two_tags(make_client, storage_path):
    """The second upload of an identical package adds a reference only."""
    with make_client() as client:
        first = client.put(f"/nightly/{IDENTITY}", content=PAYLOAD).json()
        second = client.put(f"/release/{IDENTITY}", content=PAYLOAD).json()

        assert first["deduplicated"] is False
        assert second["deduplicated"] is True
        assert second["size"] == len(PAYLOAD)

        # Exactly one copy of the payload on disk, at the identity key.
        assert blob_count(storage_path) == 1
        assert identity_blob(storage_path).read_bytes() == PAYLOAD
        assert not scoped_blob(storage_path, "release").exists()

        # Both tags reference it and both can read it.
        assert refs_document(storage_path)["namespaces"] == ["nightly", "release"]
        assert tag_entry(storage_path, "nightly").exists()
        assert tag_entry(storage_path, "release").exists()
        assert client.get(f"/nightly/{IDENTITY}").content == PAYLOAD
        assert client.get(f"/release/{IDENTITY}").content == PAYLOAD


def test_reference_counting_survives_partial_delete(make_client, storage_path):
    """Deleting from one tag leaves other referencing tags working."""
    with make_client() as client:
        client.put(f"/nightly/{IDENTITY}", content=PAYLOAD)
        client.put(f"/release/{IDENTITY}", content=PAYLOAD)

        assert client.delete(f"/nightly/{IDENTITY}").status_code == 200

        # Gone from nightly, still served from release, bytes still on disk.
        assert client.head(f"/nightly/{IDENTITY}").status_code == 404
        assert client.get(f"/release/{IDENTITY}").content == PAYLOAD
        assert identity_blob(storage_path).exists()
        assert refs_document(storage_path)["namespaces"] == ["release"]
        assert not tag_entry(storage_path, "nightly").exists()

        # The last reference removes the bytes.
        assert client.delete(f"/release/{IDENTITY}").status_code == 200
        assert not identity_blob(storage_path).exists()
        assert not (storage_path / REFS_PREFIX / f"{IDENTITY}.json").exists()


def test_second_upload_to_same_tag_conflicts(make_client):
    """Re-uploading into the same tag is still a conflict."""
    with make_client() as client:
        assert client.put(f"/nightly/{IDENTITY}", content=PAYLOAD).status_code == 200
        assert client.put(f"/nightly/{IDENTITY}", content=PAYLOAD).status_code == 409


def test_delete_unknown_tagged_package_is_404(make_client):
    """Deleting a package a tag does not hold reports 404."""
    with make_client() as client:
        client.put(f"/nightly/{IDENTITY}", content=PAYLOAD)
        assert client.delete(f"/release/{IDENTITY}").status_code == 404
        assert client.get(f"/nightly/{IDENTITY}").content == PAYLOAD


def test_dedupe_disabled_keeps_private_copies(make_client, storage_path):
    """With dedupe off each tag stores its own copy of the bytes."""
    with make_client(dedupe=False) as client:
        assert client.put(f"/nightly/{IDENTITY}", content=PAYLOAD).status_code == 200
        second = client.put(f"/release/{IDENTITY}", content=PAYLOAD).json()

        assert second["deduplicated"] is False
        assert blob_count(storage_path) == 2
        assert scoped_blob(storage_path, "nightly").read_bytes() == PAYLOAD
        assert scoped_blob(storage_path, "release").read_bytes() == PAYLOAD

        # Deleting one tag's copy leaves the other intact.
        assert client.delete(f"/nightly/{IDENTITY}").status_code == 200
        assert not scoped_blob(storage_path, "nightly").exists()
        assert client.get(f"/release/{IDENTITY}").content == PAYLOAD


def test_dedupe_disabled_keeps_untagged_layout(make_client, storage_path):
    """Untagged uploads keep the flat layout even with dedupe off."""
    with make_client(dedupe=False) as client:
        assert client.put(f"/{IDENTITY}", content=PAYLOAD).status_code == 200
        assert identity_blob(storage_path).read_bytes() == PAYLOAD


# ----------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------


def test_malformed_tag_is_rejected(make_client):
    """A tag that does not match the pattern is rejected, not created."""
    with make_client() as client:
        for bad_tag in ["-nightly", "night/ly", "n" * 65, ".hidden"]:
            response = client.put(f"/{bad_tag}/{IDENTITY}", content=PAYLOAD)
            assert response.status_code in {400, 404}, bad_tag


def test_default_namespace_cannot_be_addressed_as_tag(make_client):
    """The untagged namespace name is reserved."""
    with make_client() as client:
        response = client.put(f"/{DEFAULT_NAMESPACE}/{IDENTITY}", content=PAYLOAD)
        assert response.status_code == 400


def test_allowlist_rejects_unknown_tags(make_client):
    """A typo'd tag does not silently create a namespace."""
    with make_client(allowed="nightly, release") as client:
        assert client.put(f"/nightly/{IDENTITY}", content=PAYLOAD).status_code == 200

        response = client.put(f"/nightyl/{IDENTITY}", content=PAYLOAD)
        assert response.status_code == 400
        assert "allowlist" in response.json()["detail"]

        assert client.head(f"/nightyl/{IDENTITY}").status_code == 400
        assert client.get(f"/nightyl/{IDENTITY}").status_code == 400
        assert client.delete(f"/nightyl/{IDENTITY}").status_code == 400


def test_custom_pattern_is_enforced(make_client):
    """The tag pattern is configurable."""
    with make_client(pattern=r"^pr-[0-9]+$") as client:
        assert client.put(f"/pr-42/{IDENTITY}", content=PAYLOAD).status_code == 200
        assert client.put(f"/nightly/{IDENTITY}", content=PAYLOAD).status_code == 400


def test_tags_disabled_rejects_tagged_paths(make_client, storage_path):
    """With tags disabled only the untagged routes work and no index is written."""
    with make_client(enabled=False) as client:
        assert client.put(f"/nightly/{IDENTITY}", content=PAYLOAD).status_code == 404
        assert client.head(f"/nightly/{IDENTITY}").status_code == 404

        assert client.put(f"/{IDENTITY}", content=PAYLOAD).status_code == 200
        assert client.get(f"/{IDENTITY}").content == PAYLOAD

        assert identity_blob(storage_path).exists()
        assert not (storage_path / TAGS_PREFIX).exists()
        assert not (storage_path / REFS_PREFIX).exists()


# ----------------------------------------------------------------------
# Legacy layout compatibility
# ----------------------------------------------------------------------


def test_legacy_package_is_readable_untagged(make_client, storage_path):
    """A cache written before the index existed keeps working."""
    legacy = identity_blob(storage_path)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(PAYLOAD)

    with make_client() as client:
        assert client.head(f"/{IDENTITY}").status_code == 200
        assert client.get(f"/{IDENTITY}").content == PAYLOAD
        # It belongs to the untagged namespace only.
        assert client.head(f"/nightly/{IDENTITY}").status_code == 404


def test_legacy_package_is_adopted_when_tagged(make_client, storage_path):
    """Tagging a legacy package does not hide it from untagged clients."""
    legacy = identity_blob(storage_path)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(PAYLOAD)

    with make_client() as client:
        body = client.put(f"/nightly/{IDENTITY}", content=PAYLOAD).json()
        assert body["deduplicated"] is True

        assert refs_document(storage_path)["namespaces"] == [DEFAULT_NAMESPACE, "nightly"]
        assert client.get(f"/{IDENTITY}").content == PAYLOAD
        assert client.get(f"/nightly/{IDENTITY}").content == PAYLOAD

        # Removing the tag keeps the untagged reference alive.
        assert client.delete(f"/nightly/{IDENTITY}").status_code == 200
        assert client.get(f"/{IDENTITY}").content == PAYLOAD
        assert identity_blob(storage_path).exists()


def test_legacy_package_can_be_deleted_untagged(make_client, storage_path):
    """Deleting a legacy package removes the bytes."""
    legacy = identity_blob(storage_path)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(PAYLOAD)

    with make_client() as client:
        assert client.delete(f"/{IDENTITY}").status_code == 200
        assert not legacy.exists()


def test_legacy_package_still_conflicts_on_reupload(make_client, storage_path):
    """An untagged re-upload of a legacy package is a conflict, as before."""
    legacy = identity_blob(storage_path)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(PAYLOAD)

    with make_client() as client:
        assert client.put(f"/{IDENTITY}", content=PAYLOAD).status_code == 409


def test_index_documents_are_not_listed_as_packages(make_client):
    """Bookkeeping documents never show up as cached packages."""
    with make_client() as client:
        client.put(f"/nightly/{IDENTITY}", content=PAYLOAD)

        stats = client.get("/health/details").json()
        assert stats["storage"]["total_packages"] == 1


# ----------------------------------------------------------------------
# Retention
# ----------------------------------------------------------------------


def test_max_packages_per_tag_evicts_oldest(make_client, storage_path):
    """A tag over its package limit loses its oldest entries."""
    identities = [f"pkg-{index}/1.0.0/sha{index}/x64-linux" for index in range(3)]

    with make_client(max_packages_per_tag=2) as client:
        for identity in identities:
            assert client.put(f"/nightly/{identity}", content=PAYLOAD).status_code == 200

        assert client.head(f"/nightly/{identities[0]}").status_code == 404
        assert client.head(f"/nightly/{identities[1]}").status_code == 200
        assert client.head(f"/nightly/{identities[2]}").status_code == 200
        assert not (storage_path / identities[0]).exists()


def test_max_bytes_per_tag_evicts_oldest(make_client):
    """A tag over its size limit loses its oldest entries."""
    identities = [f"pkg-{index}/1.0.0/sha{index}/x64-linux" for index in range(3)]

    with make_client(max_bytes_per_tag=len(PAYLOAD) * 2) as client:
        for identity in identities:
            assert client.put(f"/nightly/{identity}", content=PAYLOAD).status_code == 200

        assert client.head(f"/nightly/{identities[0]}").status_code == 404
        assert client.head(f"/nightly/{identities[2]}").status_code == 200


def test_retention_keeps_other_tags_references(make_client, storage_path):
    """Eviction from one tag never removes bytes another tag references."""
    identities = [f"pkg-{index}/1.0.0/sha{index}/x64-linux" for index in range(3)]

    with make_client(max_packages_per_tag=2) as client:
        for identity in identities:
            client.put(f"/release/{identity}", content=PAYLOAD)
        for identity in identities:
            client.put(f"/nightly/{identity}", content=PAYLOAD)

        # release lost its oldest entry, but nightly's newest two survive and
        # the evicted object is still referenced by nightly.
        assert client.head(f"/release/{identities[0]}").status_code == 404
        assert client.head(f"/nightly/{identities[0]}").status_code == 404
        assert client.head(f"/nightly/{identities[2]}").status_code == 200
        assert (storage_path / identities[2]).exists()


def test_retention_disabled_by_default(make_client):
    """Without limits nothing is evicted."""
    identities = [f"pkg-{index}/1.0.0/sha{index}/x64-linux" for index in range(3)]

    with make_client() as client:
        for identity in identities:
            client.put(f"/nightly/{identity}", content=PAYLOAD)
        for identity in identities:
            assert client.head(f"/nightly/{identity}").status_code == 200


# ----------------------------------------------------------------------
# Routing
# ----------------------------------------------------------------------


def test_short_routes_are_not_shadowed(make_client):
    """The tagged route shape does not shadow the short application routes."""
    with make_client() as client:
        assert client.get("/health").status_code == 200
        assert client.get("/health/details").status_code == 200
        assert client.get("/metrics").status_code == 200


def test_both_path_shapes_are_registered(make_client):
    """Both the tagged and the untagged shape are part of the API."""
    with make_client() as client:
        paths = client.get("/api/openapi.json").json()["paths"]
        assert UNTAGGED_PATH in paths
        assert TAGGED_PATH in paths
        for methods in (paths[UNTAGGED_PATH], paths[TAGGED_PATH]):
            assert {"get", "put", "delete", "head"} <= set(methods)


def test_dedupe_rejects_different_bytes_without_registering_tag(make_client, storage_path):
    with make_client() as client:
        assert client.put(f"/nightly/{IDENTITY}", content=b"wrong bytes").status_code == 200
        response = client.put(f"/release/{IDENTITY}", content=PAYLOAD)
        assert response.status_code == 409
        assert "different bytes" in response.json()["detail"]
        assert client.get(f"/release/{IDENTITY}").status_code == 404
        assert refs_document(storage_path)["namespaces"] == ["nightly"]


def test_missing_object_can_be_uploaded_again(make_client, storage_path):
    with make_client() as client:
        assert client.put(f"/nightly/{IDENTITY}", content=PAYLOAD).status_code == 200
        identity_blob(storage_path).unlink()
        assert client.head(f"/nightly/{IDENTITY}").status_code == 404
        assert client.put(f"/nightly/{IDENTITY}", content=PAYLOAD).status_code == 200
        assert client.get(f"/nightly/{IDENTITY}").content == PAYLOAD


def test_missing_object_reference_can_be_deleted(make_client, storage_path):
    with make_client() as client:
        client.put(f"/nightly/{IDENTITY}", content=PAYLOAD)
        identity_blob(storage_path).unlink()
        assert client.delete(f"/nightly/{IDENTITY}").status_code == 200
        assert not tag_entry(storage_path, "nightly").exists()


def test_internal_storage_cannot_be_overwritten(make_client):
    with make_client() as client:
        for path in ["/_harbor/refs/zlib/1.3.1", "/release/_harbor/refs/zlib/1.3.1"]:
            for method in ["get", "head", "put", "delete"]:
                assert getattr(client, method)(path).status_code == 400
        assert client.put(f"/release/{IDENTITY}", content=PAYLOAD).status_code == 200


def test_dashboard_prefix_does_not_bypass_cache_auth(settings):
    from fastapi.testclient import TestClient

    from vcpkg_harbor.app import create_app

    settings.auth.enabled = True
    settings.auth.type = "token"
    settings.auth.token = "test-only-token"
    with TestClient(create_app(settings)) as client:
        for tag in ["packages", "packages-public", "stats", "stats-public", "partials"]:
            for method in ["get", "head", "put", "delete"]:
                assert getattr(client, method)(f"/{tag}/{IDENTITY}").status_code == 401
        assert client.get("/health").status_code == 200


def test_reserved_service_tag_is_rejected(make_client):
    with make_client() as client:
        assert client.put(f"/static/{IDENTITY}", content=PAYLOAD).status_code == 400


def test_dashboard_renders_with_current_template_api(make_client):
    with make_client() as client:
        for path in ["/", "/packages", "/stats", "/partials/stats-summary", "/partials/recent-packages"]:
            assert client.get(path).status_code == 200


async def test_concurrent_tag_uploads_keep_all_references(storage_path):
    import asyncio
    from vcpkg_harbor.core.config import Settings
    from vcpkg_harbor.services.cache_service import CacheService
    from vcpkg_harbor.storage.backends.filesystem import FilesystemBackend

    storage = FilesystemBackend(path=str(storage_path))
    await storage.initialize()
    service = CacheService(storage, Settings())

    async def upload(index):
        async def body():
            yield PAYLOAD[:5]
            await asyncio.sleep(0)
            yield PAYLOAD[5:]
        return await service.put_package(*IDENTITY.split("/"), body(), tag=f"tag-{index}")

    try:
        results = await asyncio.gather(*(upload(i) for i in range(12)))
        assert sum(not result.deduplicated for result in results) == 1
        assert len(refs_document(storage_path)["namespaces"]) == 12
        await asyncio.gather(*(
            service.delete_package(*IDENTITY.split("/"), tag=f"tag-{i}") for i in range(11)
        ))
        assert await service.check_exists(*IDENTITY.split("/"), tag="tag-11")
        assert refs_document(storage_path)["namespaces"] == ["tag-11"]
    finally:
        await storage.close()
