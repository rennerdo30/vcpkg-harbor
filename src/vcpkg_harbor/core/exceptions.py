"""Custom exceptions for vcpkg-harbor."""


class VcpkgHarborError(Exception):
    """Base exception for vcpkg-harbor."""

    def __init__(self, message: str, *args: object) -> None:
        self.message = message
        super().__init__(message, *args)


class PackageNotFoundError(VcpkgHarborError):
    """Raised when a package is not found in the cache."""

    def __init__(self, name: str, version: str, sha: str, triplet: str) -> None:
        self.name = name
        self.version = version
        self.sha = sha
        self.triplet = triplet
        super().__init__(f"Package not found: {name}/{version}/{sha}/{triplet}")


class PackageAlreadyExistsError(VcpkgHarborError):
    """Raised when trying to upload a package that already exists."""

    def __init__(self, name: str, version: str, sha: str, triplet: str) -> None:
        self.name = name
        self.version = version
        self.sha = sha
        self.triplet = triplet
        super().__init__(f"Package already exists: {name}/{version}/{sha}/{triplet}")


class InvalidTagError(VcpkgHarborError):
    """Raised when a build tag is malformed or not permitted."""

    def __init__(self, tag: str, reason: str) -> None:
        self.tag = tag
        self.reason = reason
        super().__init__(f"Invalid build tag {tag!r}: {reason}")


class TagsDisabledError(VcpkgHarborError):
    """Raised when a tagged request arrives while build tags are disabled."""

    def __init__(self, tag: str) -> None:
        self.tag = tag
        super().__init__(f"Build tags are disabled, cannot serve tag {tag!r}")


class StorageError(VcpkgHarborError):
    """Raised when a storage operation fails."""

    def __init__(self, message: str, cause: Exception | None = None) -> None:
        self.cause = cause
        super().__init__(message)


class StorageConnectionError(StorageError):
    """Raised when unable to connect to storage backend."""

    pass


class StorageConfigurationError(StorageError):
    """Raised when storage is misconfigured."""

    pass


class AuthenticationError(VcpkgHarborError):
    """Raised when authentication fails."""

    pass


class AuthorizationError(VcpkgHarborError):
    """Raised when authorization fails."""

    pass
