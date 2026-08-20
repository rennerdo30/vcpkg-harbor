# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Build tags** - An optional first path segment scopes the vcpkg protocol to a
  build stream: `/{tag}/{name}/{version}/{sha}/{triplet}`. Tags are isolated from
  each other and from the untagged namespace, and need no vcpkg client change
  because the tag is part of the configured base URL
- **Content deduplication with reference counting** - A package is stored once
  per identity (`name/version/sha/triplet`); tags reference it. Uploading a
  package another tag already holds stores no new bytes, and deleting it from one
  tag keeps the others working until the last reference is gone
- **Per-tag retention limits** - `VCPKG_TAGS_MAX_PACKAGES_PER_TAG` and
  `VCPKG_TAGS_MAX_BYTES_PER_TAG` evict a tag's oldest entries
- **Tag validation** - `VCPKG_TAGS_PATTERN` and `VCPKG_TAGS_ALLOWED` reject
  unknown tag names with `400` instead of silently creating a namespace
- **Storage backend metadata API** - `put_metadata`, `get_metadata`,
  `delete_metadata` and `list_metadata` let the tag index work identically on
  every backend; package operations take an optional `scope` prefix

### Changed

- Package uploads report `tag`, `namespace`, `deduplicated` and `evicted`
- `list_packages` now uses a shared key parser on every backend, so harbor's own
  bookkeeping documents are never reported as packages

### Compatibility

- The untagged routes and their storage layout are unchanged, so existing caches
  keep working with no migration. Packages written before this release stay
  readable through the untagged routes and are adopted into the default namespace
  the first time they are tagged. `VCPKG_TAGS_ENABLED=false` restores the exact
  previous behaviour

## [2.0.0] - 2025-01-19

### Added

- **Plugin-based storage architecture** - Storage backends are now plugins discovered via entry points
- **Multiple storage backends**:
  - Filesystem (default) - Local file storage
  - MinIO - S3-compatible object storage
  - AWS S3 - Native S3 support
  - Azure Blob Storage - Azure cloud storage
  - Google Cloud Storage - GCP cloud storage
- **Web dashboard** - Monitor cache statistics and browse packages
  - Real-time statistics with HTMX
  - Package browser with search
  - Storage backend indicator
- **Authentication system**:
  - Token-based authentication
  - HTTP Basic authentication
  - Configurable read/write permissions
- **Prometheus metrics** - Built-in `/metrics` endpoint for monitoring
- **Health check endpoints**:
  - `/health` - Basic health check
  - `/health/ready` - Readiness probe
  - `/health/live` - Liveness probe
  - `/health/details` - Detailed health information
- **Structured logging** - Using structlog for JSON-formatted logs
- **Development scripts**:
  - `setup-dev.sh` - Set up development environment
  - `dev-server.sh` - Start development server with hot reload
  - `test.sh` - Run test suite
  - `lint.sh` - Run linter
  - `docs.sh` - Build and serve documentation
- **MkDocs documentation** - Comprehensive documentation site
- **GitHub Actions**:
  - CI workflow for testing and linting
  - Docker image build and push
  - Release workflow

### Changed

- **Rewritten from scratch** - Complete rewrite from single-file to modular architecture
- **Default storage** - Changed from MinIO to filesystem for easier getting started
- **Configuration** - Now uses nested Pydantic Settings with `__` delimiter
- **Package structure** - Proper Python package under `src/vcpkg_harbor/`

### Removed

- Single-file `main.py` architecture (replaced with modular structure)

## [1.0.0] - 2024-XX-XX

### Added

- Initial release
- MinIO storage backend
- Basic REST API for vcpkg binary caching
- Docker support

[2.0.0]: https://github.com/rennerdo30/vcpkg-harbor/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/rennerdo30/vcpkg-harbor/releases/tag/v1.0.0
