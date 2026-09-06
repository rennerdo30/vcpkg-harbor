#!/usr/bin/env bash
# Rebuild the dashboard's vendored front-end assets.
#
# The dashboard serves Tailwind CSS and HTMX itself so it keeps working inside a
# page with a strict Content-Security-Policy and on machines without internet
# access. Both files are committed; run this script after changing
# static/src/tailwind.css, the templates' utility classes, or the pinned
# versions below.
#
# No Node.js required: the Tailwind standalone CLI is downloaded on demand.

set -euo pipefail

TAILWIND_VERSION="4.3.3"
HTMX_VERSION="2.0.10"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
STATIC_DIR="$PROJECT_DIR/src/vcpkg_harbor/static"
VENDOR_DIR="$STATIC_DIR/vendor"
CACHE_DIR="${TMPDIR:-/tmp}/vcpkg-harbor-assets"

mkdir -p "$VENDOR_DIR" "$CACHE_DIR"

case "$(uname -s)-$(uname -m)" in
    Darwin-arm64) TAILWIND_TARGET="macos-arm64" ;;
    Darwin-x86_64) TAILWIND_TARGET="macos-x64" ;;
    Linux-aarch64 | Linux-arm64) TAILWIND_TARGET="linux-arm64" ;;
    Linux-x86_64) TAILWIND_TARGET="linux-x64" ;;
    *)
        echo "Unsupported platform: $(uname -s)-$(uname -m)" >&2
        echo "Download the Tailwind CLI manually from" \
             "https://github.com/tailwindlabs/tailwindcss/releases" >&2
        exit 1
        ;;
esac

TAILWIND_CLI="$CACHE_DIR/tailwindcss-$TAILWIND_VERSION-$TAILWIND_TARGET"
if [ ! -x "$TAILWIND_CLI" ]; then
    echo "Downloading Tailwind CLI $TAILWIND_VERSION ($TAILWIND_TARGET)..."
    curl -fsSL -o "$TAILWIND_CLI" \
        "https://github.com/tailwindlabs/tailwindcss/releases/download/v$TAILWIND_VERSION/tailwindcss-$TAILWIND_TARGET"
    chmod +x "$TAILWIND_CLI"
fi

echo "Building $VENDOR_DIR/tailwind.css..."
"$TAILWIND_CLI" --input "$STATIC_DIR/src/tailwind.css" \
    --output "$VENDOR_DIR/tailwind.css" --minify

echo "Downloading HTMX $HTMX_VERSION..."
curl -fsSL -o "$VENDOR_DIR/htmx.min.js" \
    "https://cdn.jsdelivr.net/npm/htmx.org@$HTMX_VERSION/dist/htmx.min.js"

echo ""
echo "Vendored assets rebuilt. Keep the versions in"
echo "src/vcpkg_harbor/dashboard/urls.py in sync when bumping them."
ls -l "$VENDOR_DIR"
