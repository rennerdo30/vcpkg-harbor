#!/usr/bin/env bash
# Run tests with coverage

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Set test environment variables
export VCPKG_STORAGE_TYPE=filesystem
export VCPKG_STORAGE_PATH=/tmp/vcpkg-harbor-test
export VCPKG_LOG_LEVEL=DEBUG
export VCPKG_LOG_FILE=

# Clean up test directory
rm -rf "$VCPKG_STORAGE_PATH"
mkdir -p "$VCPKG_STORAGE_PATH"

echo "Running tests..."
pytest tests/ -v --cov=vcpkg_harbor --cov-report=term-missing --cov-report=html "$@"

echo ""
echo "Coverage report generated in htmlcov/"
