#!/usr/bin/env bash
# Run linting and formatting checks

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

echo "Running Ruff linter..."
ruff check src/

echo ""
echo "Running Ruff formatter check..."
ruff format --check src/

echo ""
echo "Running mypy type checker..."
mypy src/vcpkg_harbor --ignore-missing-imports

echo ""
echo "All checks passed!"
