#!/usr/bin/env bash
# Start development server with auto-reload

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Set development defaults
export VCPKG_SERVER_RELOAD=${VCPKG_SERVER_RELOAD:-true}
export VCPKG_SERVER_WORKERS=${VCPKG_SERVER_WORKERS:-1}
export VCPKG_LOG_LEVEL=${VCPKG_LOG_LEVEL:-DEBUG}
export VCPKG_LOG_JSON=${VCPKG_LOG_JSON:-false}
export VCPKG_STORAGE_TYPE=${VCPKG_STORAGE_TYPE:-filesystem}
export VCPKG_STORAGE_PATH=${VCPKG_STORAGE_PATH:-./cache}

# Create cache directory for filesystem backend
mkdir -p "$VCPKG_STORAGE_PATH"
mkdir -p logs

echo "Starting vcpkg-harbor development server..."
echo "  Storage: $VCPKG_STORAGE_TYPE"
echo "  Path: $VCPKG_STORAGE_PATH"
echo "  Log Level: $VCPKG_LOG_LEVEL"
echo ""

# Run with uvicorn directly for hot reload support
python -m uvicorn vcpkg_harbor.app:create_app --factory --reload --host 0.0.0.0 --port 15151 --log-level debug
