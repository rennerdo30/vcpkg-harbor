<p align="center">
  <img src="docs/assets/logo.svg" alt="vcpkg-harbor logo" width="200">
</p>

<h1 align="center">vcpkg-harbor</h1>

<p align="center">
  <strong>A high-performance binary cache server for <a href="https://github.com/microsoft/vcpkg">vcpkg</a></strong>
</p>

<p align="center">
  <a href="https://github.com/rennerdo30/vcpkg-harbor/actions/workflows/ci.yml"><img src="https://github.com/rennerdo30/vcpkg-harbor/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/rennerdo30/vcpkg-harbor/actions/workflows/docker-image.yml"><img src="https://github.com/rennerdo30/vcpkg-harbor/actions/workflows/docker-image.yml/badge.svg" alt="Docker"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+"></a>
  <a href="https://pypi.org/project/vcpkg-harbor/"><img src="https://img.shields.io/pypi/v/vcpkg-harbor.svg" alt="PyPI version"></a>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#documentation">Documentation</a> •
  <a href="#contributing">Contributing</a>
</p>

---

vcpkg-harbor caches compiled C++ packages, allowing teams to share pre-built binaries and dramatically reduce build times. It supports multiple storage backends and provides a web dashboard for monitoring.

## Features

- 🚀 **Multiple Storage Backends** - MinIO, AWS S3, Azure Blob, Google Cloud Storage, or local filesystem
- 🔌 **Plugin Architecture** - Easy to add custom storage backends via entry points
- 📊 **Web Dashboard** - Monitor cache statistics and browse packages in real-time
- 📈 **Prometheus Metrics** - Built-in metrics endpoint for monitoring and alerting
- 🔐 **Authentication** - Token and HTTP Basic authentication support
- ⚡ **High Performance** - Async Python with streaming uploads/downloads
- 🐳 **Docker Ready** - Production-ready Docker images and compose files

## Quick Start

### Option 1: Using pip (Simplest)

```bash
# Install vcpkg-harbor
pip install vcpkg-harbor

# Start with filesystem storage (default)
vcpkg-harbor
```

### Option 2: Using Docker

```bash
# Simple deployment (filesystem storage)
docker run -d -p 15151:15151 -v vcpkg-cache:/app/cache \
  ghcr.io/rennerdo30/vcpkg-harbor:latest

# Or with Docker Compose (includes MinIO)
git clone https://github.com/rennerdo30/vcpkg-harbor.git
cd vcpkg-harbor
docker-compose up -d
```

### Option 3: From Source

```bash
git clone https://github.com/rennerdo30/vcpkg-harbor.git
cd vcpkg-harbor
./run.sh
```

### Configure vcpkg

```bash
# Set environment variable
export VCPKG_BINARY_SOURCES="http,http://localhost:15151/{name}/{version}/{sha}"

# Install packages (binaries will be cached)
vcpkg install zlib boost
```

## Storage Backends

| Backend | Use Case | Configuration |
|---------|----------|---------------|
| **Filesystem** (default) | Development, small teams | `VCPKG_STORAGE_TYPE=filesystem` |
| **MinIO** | On-premises, S3-compatible | `VCPKG_STORAGE_TYPE=minio` |
| **AWS S3** | AWS deployments | `VCPKG_STORAGE_TYPE=s3` |
| **Azure Blob** | Azure deployments | `VCPKG_STORAGE_TYPE=azure` |
| **Google Cloud Storage** | GCP deployments | `VCPKG_STORAGE_TYPE=gcs` |

## Configuration

vcpkg-harbor is configured via environment variables:

```bash
# Server
VCPKG_SERVER_HOST=0.0.0.0
VCPKG_SERVER_PORT=15151

# Storage (filesystem is default)
VCPKG_STORAGE_TYPE=filesystem
VCPKG_STORAGE_PATH=./cache

# Logging
VCPKG_LOG_LEVEL=INFO

# Authentication (optional)
VCPKG_AUTH_ENABLED=true
VCPKG_AUTH_TYPE=token
VCPKG_AUTH_TOKEN=your-secret-token
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/{name}/{version}/{sha}` | HEAD | Check if package exists |
| `/{name}/{version}/{sha}` | GET | Download package |
| `/{name}/{version}/{sha}` | PUT | Upload package |
| `/health` | GET | Health check |
| `/metrics` | GET | Prometheus metrics |
| `/` | GET | Web dashboard |

## Documentation

📚 **[Full Documentation](https://rennerdo30.github.io/vcpkg-harbor/)**

- [Installation](https://rennerdo30.github.io/vcpkg-harbor/getting-started/installation/)
- [Quick Start](https://rennerdo30.github.io/vcpkg-harbor/getting-started/quickstart/)
- [Configuration](https://rennerdo30.github.io/vcpkg-harbor/getting-started/configuration/)
- [Storage Backends](https://rennerdo30.github.io/vcpkg-harbor/user-guide/storage-backends/)
- [Docker Deployment](https://rennerdo30.github.io/vcpkg-harbor/deployment/docker/)
- [Kubernetes Deployment](https://rennerdo30.github.io/vcpkg-harbor/deployment/kubernetes/)

## Development

```bash
# Setup development environment
./scripts/setup-dev.sh

# Start development server
./scripts/dev-server.sh

# Run tests
./scripts/test.sh

# Run linter
./scripts/lint.sh
```

## Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) for details.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [vcpkg](https://github.com/microsoft/vcpkg) - C++ package manager by Microsoft
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [MinIO](https://min.io/) - High-performance object storage
