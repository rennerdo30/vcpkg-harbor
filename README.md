# vcpkg-harbor

A binary cache server for vcpkg, Microsoft's C++ package manager.

## Features

- Binary package caching using MinIO storage backend
- Streaming uploads and downloads
- Environment-based configuration
- Comprehensive logging
- Docker support
- Multi-worker deployment support
- Read-only and write-only modes

## Prerequisites

- Python 3.8+
- MinIO server (can be run via Docker)
- Docker (optional, for containerized deployment)

## Installation

### Local Development Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/vcpkg-harbor.git
cd vcpkg-harbor
```

2. Create a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# OR
.venv\Scripts\activate     # Windows
```

3. Install dependencies:
```bash
pip install fastapi uvicorn minio pydantic-settings
```

### Docker Setup

1. Using docker-compose:
```bash
docker-compose up -d
```

2. Using Docker directly:
```bash
docker build -t vcpkg-harbor .
docker run -d -p 15151:15151 vcpkg-harbor
```

## Configuration

Create a `.env` file in the project root:

```env
# Server settings
VCPKG_HOST=0.0.0.0
VCPKG_PORT=15151
VCPKG_WORKERS=4
VCPKG_READ_ONLY=false
VCPKG_WRITE_ONLY=false

# Storage settings
VCPKG_STORAGE_TYPE=minio
VCPKG_STORAGE_PATH=./cache

# MinIO settings
VCPKG_MINIO_ENDPOINT=localhost:9000
VCPKG_MINIO_ACCESS_KEY=minioadmin
VCPKG_MINIO_SECRET_KEY=minioadmin
VCPKG_MINIO_BUCKET=vcpkg-harbor
VCPKG_MINIO_SECURE=false

# Logging settings
VCPKG_LOG_LEVEL=INFO
VCPKG_LOG_JSON=false
VCPKG_LOG_FILE=logs/vcpkg-harbor.log
VCPKG_LOG_RETENTION_DAYS=30
```

## Usage

### Starting the Server

#### Using Scripts

Linux/Mac:
```bash
./run.sh
```

Windows:
```bash
run.bat
```

#### Manual Start

```bash
python main.py
```

### Configuring vcpkg

Add the binary cache to your vcpkg configuration:

```bash
export VCPKG_BINARY_SOURCES="http,http://localhost:15151/{name}/{version}/{sha}"
```

### API Endpoints

1. Check Package Existence:
```bash
HEAD /{name}/{version}/{sha}
```

2. Download Package:
```bash
GET /{name}/{version}/{sha}
```

3. Upload Package:
```bash
PUT /{name}/{version}/{sha}
```

## Testing

1. Start MinIO:
```bash
docker run -d -p 9000:9000 -p 9001:9001 minio/minio server /data
```

2. Start vcpkg-harbor:
```bash
python main.py
```

3. Configure vcpkg:
```bash
export VCPKG_BINARY_SOURCES="http,http://localhost:15151/{name}/{version}/{sha}"
```

4. Test with vcpkg:
```bash
vcpkg install some-package
```

## Production Deployment

For production deployment, consider:

1. Enable SSL/TLS
2. Configure proper authentication
3. Use a production-grade MinIO setup
4. Set up monitoring and alerting
5. Configure proper logging
6. Use a reverse proxy (e.g., nginx)

## Logs

Logs are stored in `logs/vcpkg-harbor.log` by default. The logging system features:

- Log rotation (daily)
- Configurable retention period
- JSON format support
- Multiple log levels
- Console and file output

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Create a new Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.