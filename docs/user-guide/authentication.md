# Authentication

vcpkg-harbor supports optional authentication to secure your binary cache.

## Authentication Types

### No Authentication (Default)

By default, authentication is disabled. Anyone can read and write to the cache.

```bash
VCPKG_AUTH_ENABLED=false
```

### Token Authentication

Use a static API token for simple authentication.

```bash
VCPKG_AUTH_ENABLED=true
VCPKG_AUTH_TYPE=token
VCPKG_AUTH_TOKEN=your-secret-token
```

Clients must include the token in requests:

```bash
# Using curl
curl -H "Authorization: Bearer your-secret-token" http://localhost:15151/health

# vcpkg configuration (in vcpkg-configuration.json)
{
  "binary-sources": [
    {
      "kind": "http",
      "uri": "http://localhost:15151/{name}/{version}/{sha}",
      "headers": {
        "Authorization": "Bearer your-secret-token"
      }
    }
  ]
}
```

### HTTP Basic Authentication

Use username/password authentication.

```bash
VCPKG_AUTH_ENABLED=true
VCPKG_AUTH_TYPE=basic
VCPKG_AUTH_BASIC_USERS=admin:password,user:pass123
```

Clients authenticate with standard HTTP Basic auth:

```bash
# Using curl
curl -u admin:password http://localhost:15151/health

# vcpkg with basic auth URL
export VCPKG_BINARY_SOURCES="http,http://admin:password@localhost:15151/{name}/{version}/{sha}"
```

## Public Endpoints

The following endpoints are always public (no authentication required):

- `/health` - Health check
- `/health/live` - Liveness probe
- `/health/ready` - Readiness probe
- `/metrics` - Prometheus metrics
- `/` - Dashboard (when enabled)
- `/packages/*` - Package browsing (dashboard)
- `/stats` - Statistics (dashboard)

## Security Recommendations

!!! warning "Production Security"
    For production deployments:

    1. **Use HTTPS**: Deploy behind a reverse proxy with TLS
    2. **Strong tokens**: Generate cryptographically secure tokens
    3. **Rotate credentials**: Regularly rotate API tokens
    4. **Network isolation**: Use private networks where possible

### Generating Secure Tokens

```bash
# Generate a random token
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Reverse Proxy with TLS

Example nginx configuration:

```nginx
server {
    listen 443 ssl;
    server_name vcpkg-cache.example.com;

    ssl_certificate /etc/ssl/certs/vcpkg-cache.crt;
    ssl_certificate_key /etc/ssl/private/vcpkg-cache.key;

    location / {
        proxy_pass http://localhost:15151;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```
