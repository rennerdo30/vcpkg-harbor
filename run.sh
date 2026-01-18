#!/bin/bash
# Quick start script for vcpkg-harbor

set -e

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e .
else
    source .venv/bin/activate
fi

# Create directories
mkdir -p logs cache

# Set defaults for local filesystem storage
export VCPKG_STORAGE_TYPE=${VCPKG_STORAGE_TYPE:-filesystem}
export VCPKG_STORAGE_PATH=${VCPKG_STORAGE_PATH:-./cache}

echo "Starting vcpkg-harbor..."
vcpkg-harbor
