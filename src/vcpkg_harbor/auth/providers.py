"""Authentication providers for vcpkg-harbor."""

import base64
import hashlib
import secrets
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from starlette.requests import Request

logger = structlog.get_logger(__name__)


class AuthProvider(ABC):
    """Base class for authentication providers."""

    @abstractmethod
    async def authenticate(self, request: "Request") -> bool:
        """Authenticate a request.

        Args:
            request: The incoming request

        Returns:
            True if authenticated, False otherwise
        """
        ...

    @abstractmethod
    def get_user(self, request: "Request") -> str | None:
        """Get the authenticated user from a request.

        Args:
            request: The incoming request

        Returns:
            Username if authenticated, None otherwise
        """
        ...


class NoAuthProvider(AuthProvider):
    """No authentication - allows all requests."""

    async def authenticate(self, request: "Request") -> bool:
        """Always returns True (no authentication)."""
        return True

    def get_user(self, request: "Request") -> str | None:
        """Returns 'anonymous' for all requests."""
        return "anonymous"


class TokenAuthProvider(AuthProvider):
    """Token-based authentication using Bearer tokens."""

    def __init__(self, token: str) -> None:
        """Initialize with expected token.

        Args:
            token: The expected API token
        """
        # Store hash of token for constant-time comparison
        self._token_hash = hashlib.sha256(token.encode()).digest()

    async def authenticate(self, request: "Request") -> bool:
        """Authenticate using Bearer token."""
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            logger.debug("Missing or invalid Authorization header")
            return False

        token = auth_header[7:]  # Remove "Bearer " prefix

        # Constant-time comparison
        token_hash = hashlib.sha256(token.encode()).digest()
        if secrets.compare_digest(token_hash, self._token_hash):
            return True

        logger.warning("Invalid token provided")
        return False

    def get_user(self, request: "Request") -> str | None:
        """Returns 'api-token' for authenticated requests."""
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return "api-token"
        return None


class BasicAuthProvider(AuthProvider):
    """HTTP Basic authentication."""

    def __init__(self, users: dict[str, str]) -> None:
        """Initialize with user credentials.

        Args:
            users: Dictionary of username -> password
        """
        # Store password hashes
        self._users: dict[str, bytes] = {}
        for username, password in users.items():
            self._users[username] = hashlib.sha256(password.encode()).digest()

    @classmethod
    def from_string(cls, users_string: str) -> "BasicAuthProvider":
        """Create from comma-separated user:password string.

        Args:
            users_string: Format: "user1:pass1,user2:pass2"

        Returns:
            BasicAuthProvider instance
        """
        users = {}
        for pair in users_string.split(","):
            pair = pair.strip()
            if ":" in pair:
                username, password = pair.split(":", 1)
                users[username.strip()] = password.strip()
        return cls(users)

    async def authenticate(self, request: "Request") -> bool:
        """Authenticate using HTTP Basic auth."""
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Basic "):
            logger.debug("Missing or invalid Authorization header")
            return False

        try:
            credentials = base64.b64decode(auth_header[6:]).decode()
            username, password = credentials.split(":", 1)
        except Exception:
            logger.warning("Failed to decode Basic auth credentials")
            return False

        if username not in self._users:
            logger.warning("Unknown user attempted authentication", user=username)
            return False

        # Constant-time comparison
        password_hash = hashlib.sha256(password.encode()).digest()
        if secrets.compare_digest(password_hash, self._users[username]):
            logger.debug("User authenticated", user=username)
            return True

        logger.warning("Invalid password for user", user=username)
        return False

    def get_user(self, request: "Request") -> str | None:
        """Get username from Basic auth header."""
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Basic "):
            return None

        try:
            credentials = base64.b64decode(auth_header[6:]).decode()
            username, _ = credentials.split(":", 1)
            return username
        except Exception:
            return None
