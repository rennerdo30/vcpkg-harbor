# vcpkg-harbor

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104.0+-00a393.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A high-performance binary cache server for vcpkg that supports both local filesystem and MinIO storage backends.

## Features

- Filesystem and MinIO storage support
- High-performance async I/O operations
- Structured logging with file output
- Docker support with configurable deployment
- Health checks and Prometheus metrics
- Read-only and write-only modes
- CORS support
- Multi-worker configuration

## Quick Start

### Using Docker (Recommended)

```bash
# Start the server with MinIO
docker compose up -d

# Configure vcpkg to use the cache
export VCPKG_BINARY_SOURCES="http,http://localhost:15151/{name}/{version}/{sha}"
```

Access the MinIO console at http://localhost:9001 (default credentials: minioadmin/minioadmin).

### Manual Installation

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Start the server
./run.sh  # Linux/macOS
run.bat   # Windows
```

## Configuration

### Environment Variables

```bash
# Server
VCPKG_HOST=0.0.0.0
VCPKG_PORT=15151
VCPKG_WORKERS=4

# Storage
VCPKG_STORAGE_TYPE=minio  # or 'file'
VCPKG_STORAGE_PATH=./cache  # for file storage

# MinIO
VCPKG_MINIO_ENDPOINT=minio:9000
VCPKG_MINIO_ACCESS_KEY=minioadmin
VCPKG_MINIO_SECRET_KEY=minioadmin
VCPKG_MINIO_BUCKET=vcpkg-harbor
VCPKG_MINIO_SECURE=false

# Logging
VCPKG_LOG_LEVEL=INFO
VCPKG_LOG_JSON=true
VCPKG_LOG_FILE=logs/vcpkg-harbor.log

# Operation Mode
VCPKG_READ_ONLY=false
VCPKG_WRITE_ONLY=false
```

### Run Scripts

Both Windows (`run.bat`) and Unix (`run.sh`) scripts support:

```bash
Options:
  --help          Show help message
  --prod          Run in production mode
  --dev           Run in development mode (default)
  --port <port>   Set port number
  --host <host>   Set host address
  --storage <type> Set storage type (file/minio)
  --path <path>   Set storage path
  --log-level <level> Set log level
  --workers <num> Set number of workers
  --docker        Run using Docker
  --docker-dev    Run using Docker in development mode
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/{name}/{version}/{sha}` | HEAD | Check if package exists |
| `/{name}/{version}/{sha}` | GET | Download package |
| `/{name}/{version}/{sha}` | PUT | Upload package |
| `/` | GET | Health check |
| `/metrics` | GET | Prometheus metrics |

## Docker Deployment

### Basic Setup

```bash
# Production deployment
docker compose up -d

# Development with hot reload
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

### Available Services

- vcpkg-harbor (`:15151`): Main server
- MinIO (`:9000`, `:9001`): Object storage
- Prometheus (`:9090`): Metrics (optional)
- Grafana (`:3000`): Dashboards (optional)

### Monitoring

Enable monitoring services:

```bash
docker compose --profile monitoring up -d
```

## Development

### Running Tests

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# Run with coverage
pytest --cov=app tests/
```

### Code Style

```bash
# Format code
black app/ tests/

# Check types
mypy app/

# Lint code
flake8 app/ tests/
```

## Production Setup

1. Configure environment:
```bash
cp .env.example .env
# Edit .env with your settings
```

2. Use production profile:
```bash
docker compose --profile production up -d
```

3. Configure Traefik (included in production profile):
   - Add SSL certificates
   - Configure domains
   - Set up authentication if needed

## Contributing

1. Fork the repository
2. Create a feature branch
3. Run tests
4. Submit pull request

## License

[MIT License](LICENSE)

## Support

- File issues in the Github issue tracker
- Check the documentation in the `docs` directory
- Read [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines