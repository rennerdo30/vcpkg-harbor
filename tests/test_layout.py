"""Tests for the shared storage key layout."""

import pytest

from vcpkg_harbor.storage.layout import (
    InvalidKeyError,
    PackageKey,
    object_key,
    package_key_from_entry_key,
    parse_object_key,
    refs_key,
    tag_entry_key,
    tag_object_scope,
)

KEY = PackageKey("zlib", "1.3.1", "abc123", "x64-linux")


def test_identity_key_is_the_legacy_layout():
    """An unscoped key is byte identical to the pre-tag layout."""
    assert object_key("zlib", "1.3.1", "abc123", "x64-linux") == "zlib/1.3.1/abc123/x64-linux"
    assert KEY.path == "zlib/1.3.1/abc123/x64-linux"


def test_scoped_key_is_prefixed():
    """A scoped key lives below the reserved prefix."""
    key = object_key("zlib", "1.3.1", "abc123", "x64-linux", tag_object_scope("nightly"))
    assert key == "_harbor/objects/nightly/zlib/1.3.1/abc123/x64-linux"


@pytest.mark.parametrize("segment", ["..", ".", "", "a/b"])
def test_unsafe_segments_are_rejected(segment):
    """Key segments that could escape the storage root are refused."""
    with pytest.raises(InvalidKeyError):
        object_key(segment, "1.3.1", "abc123", "x64-linux")
    with pytest.raises(InvalidKeyError):
        tag_object_scope(segment)


def test_parse_identity_key():
    """An identity key parses back with no tag."""
    parsed = parse_object_key("zlib/1.3.1/abc123/x64-linux")
    assert parsed is not None
    assert parsed.tag is None
    assert parsed.key == KEY


def test_parse_scoped_key():
    """A tag scoped key parses back with its tag."""
    parsed = parse_object_key("_harbor/objects/nightly/zlib/1.3.1/abc123/x64-linux")
    assert parsed is not None
    assert parsed.tag == "nightly"
    assert parsed.key == KEY


@pytest.mark.parametrize(
    "key",
    [
        "zlib",
        "zlib/1.3.1",
        "zlib/1.3.1/abc123",
        "_harbor/refs/zlib/1.3.1/abc123/x64-linux.json",
        "_harbor/tags/nightly/zlib/1.3.1/abc123/x64-linux.json",
        "_harbor/objects/nightly/zlib/1.3.1/abc123",
    ],
)
def test_non_package_keys_are_not_parsed(key):
    """Bookkeeping documents and short keys are not packages."""
    assert parse_object_key(key) is None


def test_bookkeeping_keys_round_trip():
    """A tag entry key parses back into the package identity."""
    entry_key = tag_entry_key("nightly", KEY)
    assert entry_key == "_harbor/tags/nightly/zlib/1.3.1/abc123/x64-linux.json"
    assert package_key_from_entry_key("nightly", entry_key) == KEY
    assert package_key_from_entry_key("release", entry_key) is None
    assert refs_key(KEY) == "_harbor/refs/zlib/1.3.1/abc123/x64-linux.json"
