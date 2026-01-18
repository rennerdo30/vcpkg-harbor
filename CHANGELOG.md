# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
