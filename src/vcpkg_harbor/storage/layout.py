"""Object key layout shared by all storage backends.

Every backend stores packages under the same logical key so that a cache can be
moved between backends without a rewrite. Two shapes exist:

``{name}/{version}/{sha}/{triplet}``
    The *identity* key. A vcpkg package is fully identified by this 4-tuple
    (``sha`` is the ABI hash), so the identity key is also the deduplication
    key: the same package uploaded under several build tags is stored once and
    the tag index holds a reference to it. This is the historical layout, which
    keeps existing caches readable without migration.

``_harbor/objects/{tag}/{name}/{version}/{sha}/{triplet}``
    A *tag scoped* key, used only when deduplication is disabled and every tag
    is supposed to own a private copy of the bytes.

Harbor's own bookkeeping lives under the reserved ``_harbor/`` prefix, which
cannot collide with a vcpkg port name (port names are lowercase alphanumeric
with hyphens).
"""

from dataclasses import dataclass

# Top level prefix reserved for harbor bookkeeping. Never a valid port name.
RESERVED_PREFIX = "_harbor"

# Tag membership entries: _harbor/tags/{tag}/{name}/{version}/{sha}/{triplet}.json
TAGS_PREFIX = f"{RESERVED_PREFIX}/tags"

# Reference counters: _harbor/refs/{name}/{version}/{sha}/{triplet}.json
REFS_PREFIX = f"{RESERVED_PREFIX}/refs"

# Tag private object copies (deduplication disabled): _harbor/objects/{tag}/...
OBJECTS_PREFIX = f"{RESERVED_PREFIX}/objects"

# Suffix used for all bookkeeping documents.
METADATA_SUFFIX = ".json"

# Number of segments in an identity key.
IDENTITY_SEGMENTS = 4

# Number of segments in a tag scoped object key.
SCOPED_OBJECT_SEGMENTS = 3 + IDENTITY_SEGMENTS

# Segments that must never appear in a storage key.
_UNSAFE_SEGMENTS = frozenset({"", ".", ".."})


@dataclass(frozen=True, slots=True)
class PackageKey:
    """The identity of a cached package.

    vcpkg identifies a binary package by name, version, ABI hash and triplet;
    two uploads sharing all four are byte-identical by construction.
    """

    name: str
    version: str
    sha: str
    triplet: str

    @property
    def path(self) -> str:
        """The identity key, i.e. ``name/version/sha/triplet``."""
        return f"{self.name}/{self.version}/{self.sha}/{self.triplet}"

    def __str__(self) -> str:
        return self.path


@dataclass(frozen=True, slots=True)
class ParsedObjectKey:
    """A storage key parsed back into a package identity plus optional tag."""

    key: PackageKey
    tag: str | None = None


class InvalidKeyError(ValueError):
    """Raised when a storage key contains unsafe path segments."""


def _check_segments(*segments: str) -> None:
    """Reject key segments that could escape the storage root."""
    for segment in segments:
        if segment in _UNSAFE_SEGMENTS or "/" in segment or "\\" in segment:
            raise InvalidKeyError(f"Unsafe storage key segment: {segment!r}")


def object_key(
    name: str,
    version: str,
    sha: str,
    triplet: str,
    scope: str | None = None,
) -> str:
    """Build the storage key for a package.

    Args:
        name: Package name
        version: Package version
        sha: Package ABI hash
        triplet: Target triplet
        scope: Optional key prefix. ``None`` yields the identity key, which is
            what deduplicated (and legacy) storage uses.

    Returns:
        The storage key, using ``/`` separators on every backend.

    Raises:
        InvalidKeyError: If any component contains unsafe path segments.
    """
    _check_segments(name, version, sha, triplet)
    identity = f"{name}/{version}/{sha}/{triplet}"
    if not scope:
        return identity
    return f"{scope.strip('/')}/{identity}"


def tag_object_scope(tag: str) -> str:
    """Return the object scope that holds a tag's private copies."""
    _check_segments(tag)
    return f"{OBJECTS_PREFIX}/{tag}"


def tag_entry_key(tag: str, key: PackageKey) -> str:
    """Return the bookkeeping key for one package's membership in a tag."""
    _check_segments(tag)
    _check_segments(key.name, key.version, key.sha, key.triplet)
    return f"{TAGS_PREFIX}/{tag}/{key.path}{METADATA_SUFFIX}"


def tag_entry_prefix(tag: str) -> str:
    """Return the bookkeeping prefix holding all entries of a tag."""
    _check_segments(tag)
    return f"{TAGS_PREFIX}/{tag}/"


def refs_key(key: PackageKey) -> str:
    """Return the bookkeeping key holding a package's reference counter."""
    _check_segments(key.name, key.version, key.sha, key.triplet)
    return f"{REFS_PREFIX}/{key.path}{METADATA_SUFFIX}"


def package_key_from_entry_key(tag: str, entry_key: str) -> PackageKey | None:
    """Recover the package identity from a tag membership key.

    Args:
        tag: The tag the entry belongs to
        entry_key: A key previously produced by :func:`tag_entry_key`

    Returns:
        The package identity, or ``None`` if the key does not have the expected
        shape (for instance a stray object under the tag prefix).
    """
    prefix = tag_entry_prefix(tag)
    if not entry_key.startswith(prefix) or not entry_key.endswith(METADATA_SUFFIX):
        return None
    remainder = entry_key[len(prefix) : -len(METADATA_SUFFIX)]
    parts = remainder.split("/")
    if len(parts) != IDENTITY_SEGMENTS:
        return None
    return PackageKey(*parts)


def is_reserved_key(key: str) -> bool:
    """Whether a key belongs to harbor's reserved bookkeeping namespace."""
    return key == RESERVED_PREFIX or key.startswith(f"{RESERVED_PREFIX}/")


def parse_object_key(key: str) -> ParsedObjectKey | None:
    """Parse a storage key back into a package identity.

    Used by every backend's ``list_packages`` so that listings behave the same
    everywhere and bookkeeping documents are never reported as packages.

    Args:
        key: A storage key using ``/`` separators

    Returns:
        The parsed identity, or ``None`` if the key is not a package object
        (bookkeeping documents, or keys that are too short).
    """
    parts = key.strip("/").split("/")

    if parts and parts[0] == RESERVED_PREFIX:
        # Only tag scoped object copies are packages; refs/tags are bookkeeping.
        if len(parts) != SCOPED_OBJECT_SEGMENTS or parts[1] != "objects":
            return None
        tag = parts[2]
        return ParsedObjectKey(key=PackageKey(*parts[3:SCOPED_OBJECT_SEGMENTS]), tag=tag)

    if len(parts) < IDENTITY_SEGMENTS:
        return None

    return ParsedObjectKey(key=PackageKey(*parts[:IDENTITY_SEGMENTS]), tag=None)
