# Quick Start

Get vcpkg-harbor running in under 5 minutes.

## Option 1: Docker Compose (Recommended)

This starts vcpkg-harbor with MinIO for storage:

```bash
# Clone and start
git clone https://github.com/rennerdo30/vcpkg-harbor.git
cd vcpkg-harbor
docker-compose up -d
```

Services:
- vcpkg-harbor: `http://localhost:15151`
- MinIO Console: `http://localhost:9001` (admin: minioadmin/minioadmin)

## Option 2: Local Filesystem

For quick testing without external dependencies:

```bash
# Install
pip install vcpkg-harbor

# Start with filesystem storage
VCPKG_STORAGE_TYPE=filesystem VCPKG_STORAGE_PATH=./cache vcpkg-harbor
```

## Configure vcpkg Client

Add the binary cache to your vcpkg configuration:

=== "Environment Variable"
    ```bash
    export VCPKG_BINARY_SOURCES="http,http://localhost:15151/{name}/{version}/{sha}"
    ```

=== "vcpkg Configuration"
    Add to `vcpkg-configuration.json`:
    ```json
    {
      "default-registry": {
        "kind": "git",
        "repository": "https://github.com/microsoft/vcpkg"
      },
      "registries": [],
      "binary-sources": [
        {
          "kind": "http",
          "uri": "http://localhost:15151/{name}/{version}/{sha}"
        }
      ]
    }
    ```

## Test the Cache

```bash
# Install a package
vcpkg install zlib

# The binary will be cached. On next install (or on another machine),
# vcpkg will download the pre-built binary instead of compiling.
```

## Verify It's Working

1. **Check the dashboard**: Open `http://localhost:15151` in your browser
2. **Check the API**: `curl http://localhost:15151/health`
3. **View metrics**: `curl http://localhost:15151/metrics`

## Next Steps

- [Configuration](configuration.md) - Customize settings
- [Storage Backends](../user-guide/storage-backends.md) - Use cloud storage
- [Authentication](../user-guide/authentication.md) - Secure your cache
