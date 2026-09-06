"""Build tag index with content deduplication and reference counting.

A *build tag* is an optional first path segment on the vcpkg protocol routes, so
independent build streams can share one server:

* ``/{tag}/{name}/{version}/{sha}/{triplet}`` -- tagged
* ``/{name}/{version}/{sha}/{triplet}``       -- untagged, the default namespace

A package identity selects the candidate shared object. CacheService verifies
SHA-256 digests before adding a namespace reference, so an ABI hash alone never
establishes content equality. Deleting a package from one tag only drops that
tag's reference; the bytes go away when the last reference does.

Two bookkeeping documents implement this, both under the reserved ``_harbor/``
prefix and both written through the ``StorageBackend`` metadata API so every
backend behaves identically:

``_harbor/tags/{tag}/{name}/{version}/{sha}/{triplet}.json``
    One tag's membership record, holding the size, the registration timestamp
    (used for per-tag retention) and the object scope that holds the bytes.

``_harbor/refs/{name}/{version}/{sha}/{triplet}.json``
    The reference counter: the set of namespaces referencing this package.

Packages written before the index existed have no bookkeeping documents at all.
They stay readable through the untagged routes (the identity key is unchanged),
and the first time such a package is tagged it is adopted into the default
namespace so untagged clients keep seeing it.
"""

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog

from vcpkg_harbor.core.exceptions import (
    InvalidTagError,
    StorageError,
    TagsDisabledError,
)
from vcpkg_harbor.storage.layout import (
    PackageKey,
    package_key_from_entry_key,
    refs_key,
    tag_entry_key,
    tag_entry_prefix,
    tag_object_scope,
)

if TYPE_CHECKING:
    from vcpkg_harbor.core.config import Settings, TagSettings
    from vcpkg_harbor.storage.base import StorageBackend

logger = structlog.get_logger(__name__)

# Schema version of the bookkeeping documents, so future changes can migrate.
INDEX_VERSION = 1

# Number of striped locks used to serialise reference counter updates. Striping
# keeps memory bounded while still serialising concurrent updates of one package
# inside a single worker process.
LOCK_STRIPES = 64


def _as_utc(value: datetime | None) -> datetime:
    """Normalise a timestamp to an aware UTC datetime."""
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class TagEntry:
    """One package's membership in a namespace."""

    namespace: str
    key: PackageKey
    size: int
    registered_at: datetime
    scope: str | None = None


@dataclass(frozen=True, slots=True)
class RefRecord:
    """The reference counter of a single package."""

    key: PackageKey
    namespaces: tuple[str, ...]
    size: int

    @property
    def count(self) -> int:
        """Number of namespaces referencing the package."""
        return len(self.namespaces)


class TagService:
    """Maintains the build tag index, deduplication and reference counting."""

    def __init__(self, storage: "StorageBackend", settings: "Settings") -> None:
        """Initialize the tag service.

        Args:
            storage: Storage backend instance
            settings: Application settings
        """
        self.mutation_lock = asyncio.Lock()
        self.storage = storage
        self.config: TagSettings = settings.tags
        self._pattern = re.compile(self.config.pattern)
        self._locks = [asyncio.Lock() for _ in range(LOCK_STRIPES)]

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        """Whether the build tag index is active.

        When disabled harbor behaves exactly as it did before build tags
        existed: only untagged routes are served and no bookkeeping is written.
        """
        return self.config.enabled

    @property
    def default_namespace(self) -> str:
        """The namespace that untagged requests belong to."""
        return self.config.default_namespace

    def resolve_namespace(self, tag: str | None) -> str:
        """Validate a request's tag and return the namespace it addresses.

        Args:
            tag: The tag from the request path, or ``None`` for untagged requests

        Returns:
            The namespace name to operate on

        Raises:
            TagsDisabledError: If a tagged request arrives while tags are off
            InvalidTagError: If the tag is malformed or not allowlisted
        """
        if tag is None:
            return self.default_namespace

        if not self.enabled:
            raise TagsDisabledError(tag)

        if tag in {
            self.default_namespace,
            "_harbor",
            "static",
            "partials",
            "api",
            "health",
            "metrics",
        }:
            raise InvalidTagError(tag, "reserved namespace or service path")

        if not self._pattern.fullmatch(tag):
            raise InvalidTagError(tag, "does not match the configured tag pattern")

        allowlist = self.config.allowlist
        if allowlist and tag not in allowlist:
            raise InvalidTagError(tag, "not in the configured tag allowlist")

        return tag

    def object_scope(self, namespace: str) -> str | None:
        """Return the object scope that holds a namespace's bytes.

        ``None`` means the shared identity key, which is both the deduplicated
        location and the historical layout. A tag only gets a private scope when
        deduplication is switched off.
        """
        if not self.enabled or self.config.dedupe:
            return None
        if namespace == self.default_namespace:
            # Untagged bytes always stay at the legacy identity key.
            return None
        return tag_object_scope(namespace)

    # ------------------------------------------------------------------
    # Document access
    # ------------------------------------------------------------------

    def _lock_for(self, key: PackageKey) -> asyncio.Lock:
        """Return the striped lock guarding one package's reference counter."""
        return self._locks[hash(key.path) % LOCK_STRIPES]

    async def _read_document(self, storage_key: str) -> dict[str, Any] | None:
        """Read and decode a bookkeeping document."""
        raw = await self.storage.get_metadata(storage_key)
        if raw is None:
            return None
        try:
            document = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as e:
            logger.warning("Ignoring corrupt index document", key=storage_key, error=str(e))
            return None
        if not isinstance(document, dict):
            logger.warning("Ignoring malformed index document", key=storage_key)
            return None
        return document

    async def _write_document(self, storage_key: str, document: dict[str, Any]) -> None:
        """Encode and write a bookkeeping document."""
        payload = json.dumps(document, separators=(",", ":"), sort_keys=True).encode()
        await self.storage.put_metadata(storage_key, payload)

    async def get_entry(self, namespace: str, key: PackageKey) -> TagEntry | None:
        """Get a package's membership record in a namespace, if any."""
        document = await self._read_document(tag_entry_key(namespace, key))
        if document is None:
            return None
        return TagEntry(
            namespace=namespace,
            key=key,
            size=int(document.get("size", 0)),
            registered_at=self._parse_timestamp(document.get("registered_at")),
            scope=document.get("scope"),
        )

    async def get_refs(self, key: PackageKey) -> RefRecord | None:
        """Get a package's reference counter, if the package is indexed."""
        document = await self._read_document(refs_key(key))
        if document is None:
            return None
        namespaces = document.get("namespaces") or []
        if not isinstance(namespaces, list):
            namespaces = []
        return RefRecord(
            key=key,
            namespaces=tuple(str(ns) for ns in namespaces),
            size=int(document.get("size", 0)),
        )

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime:
        """Parse a stored ISO timestamp, falling back to now on bad data."""
        if isinstance(value, str):
            try:
                return _as_utc(datetime.fromisoformat(value))
            except ValueError:
                logger.warning("Ignoring unparsable index timestamp", value=value)
        return datetime.now(UTC)

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    async def is_legacy_package(self, key: PackageKey) -> bool:
        """Whether a package predates the index.

        A legacy package has bytes at the identity key but no reference counter,
        which is exactly the state left behind by a deployment that ran before
        build tags existed.
        """
        if await self.get_refs(key) is not None:
            return False
        return await self.storage.exists(key.name, key.version, key.sha, key.triplet)

    async def resolve_read(self, namespace: str, key: PackageKey) -> tuple[bool, str | None]:
        """Resolve a read for one namespace.

        Args:
            namespace: Namespace performing the read
            key: Package identity

        Returns:
            A tuple of (visible, scope). ``visible`` is False when the namespace
            holds no reference to the package, even if another namespace does.
            ``scope`` is the object scope holding the bytes.
        """
        if not self.enabled:
            # Index disabled: every request sees the flat legacy layout.
            return True, None

        entry = await self.get_entry(namespace, key)
        if entry is not None:
            return True, entry.scope

        if namespace == self.default_namespace and await self.is_legacy_package(key):
            logger.debug("Serving legacy untagged package", package=key.path)
            return True, None

        return False, None

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    async def register(
        self,
        namespace: str,
        key: PackageKey,
        size: int,
        scope: str | None = None,
        registered_at: datetime | None = None,
    ) -> RefRecord:
        """Add a namespace's reference to a package.

        Args:
            namespace: Namespace gaining the reference
            key: Package identity
            size: Package size in bytes
            scope: Object scope holding the bytes
            registered_at: Timestamp to record, defaults to now

        Returns:
            The updated reference counter
        """
        async with self._lock_for(key):
            document = {
                "version": INDEX_VERSION,
                "size": size,
                "registered_at": _as_utc(registered_at).isoformat(),
                "scope": scope,
            }
            await self._write_document(tag_entry_key(namespace, key), document)

            refs = await self.get_refs(key)
            namespaces = set(refs.namespaces) if refs else set()
            namespaces.add(namespace)
            record = RefRecord(key=key, namespaces=tuple(sorted(namespaces)), size=size)
            await self._write_refs(record)

        logger.debug(
            "Registered package in namespace",
            namespace=namespace,
            package=key.path,
            references=record.count,
        )
        return record

    async def unregister(self, namespace: str, key: PackageKey) -> int:
        """Drop a namespace's reference to a package.

        Args:
            namespace: Namespace losing the reference
            key: Package identity

        Returns:
            The number of remaining references. Zero means the bytes are no
            longer referenced and the caller should delete the object.
        """
        async with self._lock_for(key):
            await self.storage.delete_metadata(tag_entry_key(namespace, key))

            refs = await self.get_refs(key)
            if refs is None:
                # Legacy package, or an index entry that was already removed.
                return 0

            namespaces = tuple(ns for ns in refs.namespaces if ns != namespace)
            if not namespaces:
                await self.storage.delete_metadata(refs_key(key))
                remaining = 0
            else:
                await self._write_refs(RefRecord(key=key, namespaces=namespaces, size=refs.size))
                remaining = len(namespaces)

        logger.debug(
            "Unregistered package from namespace",
            namespace=namespace,
            package=key.path,
            references=remaining,
        )
        return remaining

    @staticmethod
    def should_delete_object(scope: str | None, remaining_references: int) -> bool:
        """Whether dropping a reference should also delete the stored bytes.

        Bytes at the shared identity key survive until the last namespace
        releases them. A tag private copy (deduplication disabled) belongs to
        exactly one namespace, so it always goes with the reference.

        Args:
            scope: Object scope the reference pointed at
            remaining_references: References left after the drop

        Returns:
            True if the object should be deleted
        """
        return scope is not None or remaining_references == 0

    async def _write_refs(self, record: RefRecord) -> None:
        """Persist a reference counter."""
        await self._write_document(
            refs_key(record.key),
            {
                "version": INDEX_VERSION,
                "namespaces": list(record.namespaces),
                "size": record.size,
            },
        )

    async def adopt_legacy(self, key: PackageKey) -> bool:
        """Adopt a pre-index package into the default namespace.

        Called before an upload touches storage. Without it, tagging a package
        that was uploaded before the index existed would create a reference
        counter that does not mention the default namespace, hiding the package
        from untagged clients that could read it a moment earlier.

        Args:
            key: Package identity

        Returns:
            True if a legacy package was adopted
        """
        if not self.enabled:
            return False
        async with self._lock_for(key):
            return await self._adopt_legacy_locked(key)

    async def _adopt_legacy_locked(self, key: PackageKey) -> bool:
        """Adopt a pre-index package; must hold the package's lock."""
        if await self.get_refs(key) is not None:
            return False
        if not await self.storage.exists(key.name, key.version, key.sha, key.triplet):
            return False

        try:
            info = await self.storage.stat(key.name, key.version, key.sha, key.triplet)
        except StorageError as e:
            logger.warning(
                "Could not stat legacy package for adoption",
                package=key.path,
                error=str(e),
            )
            return False

        logger.info(
            "Adopting legacy package into default namespace",
            package=key.path,
            namespace=self.default_namespace,
        )
        await self._write_document(
            tag_entry_key(self.default_namespace, key),
            {
                "version": INDEX_VERSION,
                "size": info.size,
                "registered_at": _as_utc(info.created_at).isoformat(),
                "scope": None,
            },
        )
        await self._write_refs(
            RefRecord(key=key, namespaces=(self.default_namespace,), size=info.size)
        )
        return True

    # ------------------------------------------------------------------
    # Retention
    # ------------------------------------------------------------------

    async def list_entries(self, namespace: str) -> list[TagEntry]:
        """List every package registered in a namespace."""
        entries: list[TagEntry] = []
        for entry_key in await self.storage.list_metadata(tag_entry_prefix(namespace)):
            key = package_key_from_entry_key(namespace, entry_key)
            if key is None:
                continue
            entry = await self.get_entry(namespace, key)
            if entry is not None:
                entries.append(entry)
        return entries

    async def enforce_retention(
        self,
        namespace: str,
        keep: PackageKey | None = None,
    ) -> list[PackageKey]:
        """Evict the oldest packages until a namespace is within its limits.

        Args:
            namespace: Namespace to trim
            keep: Package that must survive, typically the one just uploaded

        Returns:
            The identities that were evicted from the namespace
        """
        max_packages = self.config.max_packages_per_tag
        max_bytes = self.config.max_bytes_per_tag
        if not self.enabled or (not max_packages and not max_bytes):
            return []

        entries = await self.list_entries(namespace)
        total_bytes = sum(entry.size for entry in entries)
        total_count = len(entries)

        # Oldest registration first; the freshly uploaded package is kept.
        entries.sort(key=lambda entry: (entry.registered_at, entry.key.path))

        evicted: list[PackageKey] = []
        for entry in entries:
            over_count = bool(max_packages) and total_count > max_packages
            over_bytes = bool(max_bytes) and total_bytes > max_bytes
            if not over_count and not over_bytes:
                break
            if keep is not None and entry.key == keep:
                continue

            remaining = await self.unregister(namespace, entry.key)
            if self.should_delete_object(entry.scope, remaining):
                await self.storage.delete(
                    entry.key.name,
                    entry.key.version,
                    entry.key.sha,
                    entry.key.triplet,
                    scope=entry.scope,
                )

            total_count -= 1
            total_bytes -= entry.size
            evicted.append(entry.key)

            logger.info(
                "Evicted package for retention limit",
                namespace=namespace,
                package=entry.key.path,
                remaining_references=remaining,
            )

        return evicted
