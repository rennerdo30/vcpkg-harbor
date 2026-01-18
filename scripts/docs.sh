#!/usr/bin/env bash
# Build and serve documentation

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Install docs dependencies if needed
pip install -e ".[docs]" -q

case "${1:-serve}" in
    build)
        echo "Building documentation..."
        mkdocs build
        echo "Documentation built in site/"
        ;;
    serve)
        echo "Starting documentation server..."
        mkdocs serve
        ;;
    deploy)
        echo "Deploying documentation to GitHub Pages..."
        mkdocs gh-deploy
        ;;
    *)
        echo "Usage: $0 {build|serve|deploy}"
        exit 1
        ;;
esac
