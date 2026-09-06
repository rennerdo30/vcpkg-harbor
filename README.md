<p align="center">
  <img src="docs/public/logo.svg" alt="vcpkg-harbor logo" width="160">
</p>

<h1 align="center">vcpkg-harbor</h1>

<p align="center">
  <strong>A binary cache server for <a href="https://github.com/microsoft/vcpkg">vcpkg</a>, with pluggable storage and a web dashboard</strong>
</p>

<p align="center">
  <a href="https://github.com/rennerdo30/vcpkg-harbor/actions/workflows/ci.yml"><img src="https://github.com/rennerdo30/vcpkg-harbor/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/rennerdo30/vcpkg-harbor/actions/workflows/docker-image.yml"><img src="https://github.com/rennerdo30/vcpkg-harbor/actions/workflows/docker-image.yml/badge.svg" alt="Docker"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+"></a>
</p>

<p align="center">
  <a href="#why">Why</a> •
  <a href="#quick-start">Quick start</a> •
  <a href="#configuration">Configuration</a> •
  <a href="#dashboard">Dashboard</a> •
  <a href="#documentation">Documentation</a>
</p>

---

## Why

Building C++ dependencies from source is slow, and every machine and CI job repeats
the same work. vcpkg can push and pull the results of those builds over HTTP, so a
binary once built is reused everywhere.

vcpkg-harbor is that HTTP endpoint: it implements the vcpkg binary caching protocol
(`HEAD`/`GET`/`PUT` on `/{name}/{version}/{sha}/{triplet}`), stores the archives in
the backend of your choice, and shows you what is in the cache.

## Features

- 🚀 **Multiple storage backends** - MinIO, AWS S3, Azure Blob, Google Cloud Storage, or the local filesystem
- 🔌 **Plugin architecture** - add your own backend through the `vcpkg_harbor.storage` entry point
- 📊 **Web dashboard** - browse cached packages and watch cache statistics live
- 📈 **Prometheus metrics** - `/metrics` endpoint for monitoring and alerting
- 🔐 **Optional authentication** - static token or HTTP Basic
- ⚡ **Async and streaming** - FastAPI with streaming uploads and downloads
- 🐳 **Container images** - published to GitHub Container Registry, plus Compose files

## Quick start

### Docker

```bash
# Filesystem storage, cache kept in a named volume
docker run -d -p 15151:15151 -v vcpkg-cache:/app/cache \
  ghcr.io/rennerdo30/vcpkg-harbor:main
```

Images are published to `ghcr.io/rennerdo30/vcpkg-harbor` and tagged per branch
(`main`) and commit (`sha-…`).

### Docker Compose

```bash
git clone https://github.com/rennerdo30/vcpkg-harbor.git
cd vcpkg-harbor

docker compose -f docker-compose.simple.yml up -d   # filesystem storage
docker compose up -d                                # includes MinIO
```

### From source

```bash
git clone https://github.com/rennerdo30/vcpkg-harbor.git
cd vcpkg-harbor
./run.sh          # creates .venv, installs the package, starts the server
```

Or install it into an environment of your own — the project is not on PyPI yet, so
install it from Git:

```bash
pip install git+https://github.com/rennerdo30/vcpkg-harbor.git
vcpkg-harbor
```

The server listens on <http://localhost:15151> and uses filesystem storage in
`./cache` unless configured otherwise.

### Point vcpkg at it

```bash
export VCPKG_BINARY_SOURCES="clear;http,http://localhost:15151/{name}/{version}/{sha}/{triplet},readwrite"

vcpkg install zlib boost
```

Use `readwrite` on machines that should upload, and `read` on machines that should
only consume the cache. The dashboard home page shows the exact line for the host
you are visiting.

## Storage backends

| Backend | Use case | Configuration |
|---------|----------|---------------|
| **Filesystem** (default) | Development, single machine | `VCPKG_STORAGE_TYPE=filesystem` |
| **MinIO** | Self-hosted, S3 compatible | `VCPKG_STORAGE_TYPE=minio` |
| **AWS S3** | AWS deployments | `VCPKG_STORAGE_TYPE=s3` |
| **Azure Blob** | Azure deployments | `VCPKG_STORAGE_TYPE=azure` |
| **Google Cloud Storage** | GCP deployments | `VCPKG_STORAGE_TYPE=gcs` |

## Configuration

vcpkg-harbor is configured via environment variables, optionally loaded from a
`.env` file in the working directory. Start from the template:

```bash
cp .env.example .env
# then edit .env and replace the placeholders with your own values
```

`.env.example` lists every supported variable with placeholder values and is the
only env file tracked in git. **Never commit `.env`** - it holds your real
endpoints, access keys and tokens, and it is ignored via `.gitignore`. In Docker
or Kubernetes, prefer injecting the variables (or mounted secrets) directly
instead of shipping a `.env` file.

Common settings:

```bash
# Server
VCPKG_SERVER_HOST=0.0.0.0
VCPKG_SERVER_PORT=15151
VCPKG_SERVER_WORKERS=4
VCPKG_SERVER_READ_ONLY=false

# Storage (filesystem is the default)
VCPKG_STORAGE_TYPE=filesystem
VCPKG_STORAGE_PATH=./cache

# MinIO, when VCPKG_STORAGE_TYPE=minio
VCPKG_MINIO_ENDPOINT=localhost:9000
VCPKG_MINIO_ACCESS_KEY=…
VCPKG_MINIO_SECRET_KEY=…
VCPKG_MINIO_BUCKET=vcpkg-harbor

# Logging (console + rotating file)
VCPKG_LOG_LEVEL=INFO
VCPKG_LOG_JSON=false
VCPKG_LOG_FILE=logs/vcpkg-harbor.log

# Authentication (disabled by default)
VCPKG_AUTH_ENABLED=true
VCPKG_AUTH_TYPE=token
VCPKG_AUTH_TOKEN=your-secret-token

# Dashboard and metrics
VCPKG_DASHBOARD_ENABLED=true
VCPKG_METRICS_ENABLED=true
# local serves Tailwind and HTMX from /static; cdn loads them from jsDelivr
VCPKG_DASHBOARD_ASSETS=local

# Reverse proxy (only needed when not served from the domain root)
VCPKG_PROXY_ROOT_PATH=/harbor
VCPKG_PROXY_FORWARDED_ALLOW_IPS=10.0.0.1
# Restrict who may embed the dashboard; unset means anyone may
VCPKG_PROXY_FRAME_ANCESTORS="'self' https://portal.example.com"
```

## API endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/{name}/{version}/{sha}/{triplet}` | HEAD | Check whether a binary is cached |
| `/{name}/{version}/{sha}/{triplet}` | GET | Download a cached binary |
| `/{name}/{version}/{sha}/{triplet}` | PUT | Upload a binary |
| `/health` | GET | Liveness check |
| `/health/details` | GET | Health check including the storage backend |
| `/metrics` | GET | Prometheus metrics |
| `/api/docs` | GET | OpenAPI reference (Swagger UI) |
| `/`, `/packages`, `/stats` | GET | Web dashboard |

## Dashboard

The dashboard is served from the same process as the cache API:

- **Dashboard** - cache size, request volume, hit rate, recent uploads and the
  `VCPKG_BINARY_SOURCES` line for this server
- **Packages** - search the cache and drill into the cached builds of a package
- **Statistics** - cache and request counters, plus the largest cached builds

It is server-rendered with Jinja2 and Tailwind CSS, and refreshes its figures in
place with HTMX — no build step and no JavaScript bundle.

Every link, asset and background request is built relative to the path the
application is mounted under, so the dashboard also works behind a reverse proxy
that serves it below the domain root (`VCPKG_PROXY_ROOT_PATH=/harbor`) and inside
an `<iframe>` on another page. Tailwind and HTMX are served from `/static` by
default and no markup is inline, so a strict `Content-Security-Policy` on the
embedding page still leaves a working dashboard.

## Tech stack

- **FastAPI** and **uvicorn** for the HTTP layer
- **Pydantic Settings** for configuration
- **structlog** for structured console and file logging
- **Jinja2 + Tailwind CSS + HTMX** for the dashboard
- **prometheus-client** for metrics
- Backend SDKs: **minio**, **boto3**, **azure-storage-blob**, **google-cloud-storage**
- **Astro Starlight** for the documentation site

## Documentation

📚 **[Full documentation](https://vcpkg-harbor.docs.renner.dev/)**

- [Installation](https://vcpkg-harbor.docs.renner.dev/getting-started/installation/)
- [Quick start](https://vcpkg-harbor.docs.renner.dev/getting-started/quickstart/)
- [Configuration](https://vcpkg-harbor.docs.renner.dev/getting-started/configuration/)
- [Storage backends](https://vcpkg-harbor.docs.renner.dev/user-guide/storage-backends/)
- [Dashboard](https://vcpkg-harbor.docs.renner.dev/user-guide/dashboard/)
- [Docker deployment](https://vcpkg-harbor.docs.renner.dev/deployment/docker/)
- [Kubernetes deployment](https://vcpkg-harbor.docs.renner.dev/deployment/kubernetes/)

## Development

```bash
./scripts/setup-dev.sh    # create .venv and install dev dependencies
./scripts/dev-server.sh   # run the server with auto-reload
./scripts/test.sh         # pytest with coverage
./scripts/lint.sh         # ruff check, ruff format --check, mypy
```

The documentation site lives in [`docs/`](docs) and is built with Astro Starlight:

```bash
cd docs
npm install
npm run dev
```

## Contributing

Contributions are welcome — see the [contributing guide](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgments

- [vcpkg](https://github.com/microsoft/vcpkg) - C++ package manager by Microsoft
- [FastAPI](https://fastapi.tiangolo.com/) - Python web framework
- [MinIO](https://min.io/) - S3 compatible object storage
