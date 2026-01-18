"""Authentication module for vcpkg-harbor."""

from vcpkg_harbor.auth.middleware import AuthMiddleware
from vcpkg_harbor.auth.providers import (
    AuthProvider,
    BasicAuthProvider,
    NoAuthProvider,
    TokenAuthProvider,
)

__all__ = [
    "AuthMiddleware",
    "AuthProvider",
    "NoAuthProvider",
    "BasicAuthProvider",
    "TokenAuthProvider",
]
