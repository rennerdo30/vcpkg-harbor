# API Reference

vcpkg-harbor exposes a REST API compatible with vcpkg's HTTP binary cache protocol.

## Base URL

```
http://localhost:15151
```

## Authentication

If authentication is enabled, include the appropriate header:

- **Token auth**: `Authorization: Bearer <token>`
- **Basic auth**: `Authorization: Basic <base64(user:pass)>`

## Cache API

### Check Package Exists

Check if a package exists in the cache.

```http
HEAD /{name}/{version}/{sha}
```

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| name | string | Package name |
| version | string | Package version |
| sha | string | Package SHA hash |

**Responses:**

| Status | Description |
|--------|-------------|
| 200 | Package exists |
| 404 | Package not found |

**Example:**

```bash
curl -I http://localhost:15151/zlib/1.2.13/abc123def456
```

---

### Download Package

Download a package from the cache.

```http
GET /{name}/{version}/{sha}
```

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| name | string | Package name |
| version | string | Package version |
| sha | string | Package SHA hash |

**Responses:**

| Status | Description |
|--------|-------------|
| 200 | Binary package data (streaming) |
| 404 | Package not found |

**Example:**

```bash
curl -o package.zip http://localhost:15151/zlib/1.2.13/abc123def456
```

---

### Upload Package

Upload a package to the cache.

```http
PUT /{name}/{version}/{sha}
```

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| name | string | Package name |
| version | string | Package version |
| sha | string | Package SHA hash |

**Request Body:** Binary package data

**Responses:**

| Status | Description |
|--------|-------------|
| 200 | Upload successful |
| 409 | Package already exists |
| 403 | Server is read-only |
| 500 | Upload failed |

**Example:**

```bash
curl -X PUT --data-binary @package.zip \
  http://localhost:15151/zlib/1.2.13/abc123def456
```

**Response:**

```json
{
  "status": "success",
  "name": "zlib",
  "version": "1.2.13",
  "sha": "abc123def456",
  "size": 1234567,
  "etag": "d41d8cd98f00b204e9800998ecf8427e"
}
```

---

### Delete Package

Delete a package from the cache.

```http
DELETE /{name}/{version}/{sha}
```

**Responses:**

| Status | Description |
|--------|-------------|
| 200 | Package deleted |
| 404 | Package not found |
| 403 | Server is read-only |

---

## Health API

### Health Check

```http
GET /health
```

**Response:**

```json
{
  "status": "healthy",
  "version": "2.0.0",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

---

### Liveness Check

```http
GET /health/live
```

**Response:**

```json
{
  "status": "alive",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

---

### Readiness Check

```http
GET /health/ready
```

**Responses:**

| Status | Description |
|--------|-------------|
| 200 | Ready |
| 503 | Not ready |

---

### Detailed Health

```http
GET /health/details
```

**Response:**

```json
{
  "status": "healthy",
  "version": "2.0.0",
  "uptime": "1d 2h 30m",
  "storage": {
    "healthy": true,
    "backend": "minio",
    "total_packages": 1234,
    "total_size_bytes": 5678901234
  },
  "cache": {
    "hits": 5000,
    "misses": 500,
    "hit_rate": "90.9%"
  }
}
```

---

## Metrics API

### Prometheus Metrics

```http
GET /metrics
```

Returns metrics in Prometheus text format.

---

## OpenAPI Documentation

Interactive API documentation is available at:

- Swagger UI: `http://localhost:15151/api/docs`
- ReDoc: `http://localhost:15151/api/redoc`
- OpenAPI JSON: `http://localhost:15151/api/openapi.json`
