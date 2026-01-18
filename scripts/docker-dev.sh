#!/usr/bin/env bash
# Start development environment with Docker (including MinIO)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "Starting vcpkg-harbor development environment with Docker..."

# Build and start services
docker-compose up --build

echo ""
echo "Services stopped."
