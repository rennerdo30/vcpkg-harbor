#!/usr/bin/env bash
# Rebuild the dashboard's vendored front-end assets.
#
# The dashboard serves Tailwind CSS, HTMX and its web fonts itself so it keeps
# working inside a page with a strict Content-Security-Policy and on machines
# without internet access. All files are committed; run this script after
# changing static/src/tailwind.css, the templates' utility classes, or the
# pinned versions below.
#
# No Node.js required: the Tailwind standalone CLI is downloaded on demand.

set -euo pipefail

TAILWIND_VERSION="4.3.3"
HTMX_VERSION="4.0.0"
# Atkinson Hyperlegible Next (UI text) and Mono (package data), SIL OFL 1.1,
# served as variable-weight Latin subsets from the Fontsource builds.
FONTSOURCE_VERSION="5.3.0"
FONT_FAMILIES=("atkinson-hyperlegible-next" "atkinson-hyperlegible-mono")

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
STATIC_DIR="$PROJECT_DIR/src/vcpkg_harbor/static"
VENDOR_DIR="$STATIC_DIR/vendor"
# Fonts sit directly below static/: a URL like /static/a/b/c has four path
# segments and would be claimed by the vcpkg cache route
# /{name}/{version}/{sha}/{triplet}, which is registered first.
FONT_DIR="$STATIC_DIR/fonts"
CACHE_DIR="${TMPDIR:-/tmp}/vcpkg-harbor-assets"

mkdir -p "$VENDOR_DIR" "$FONT_DIR" "$CACHE_DIR"

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

for family in "${FONT_FAMILIES[@]}"; do
    echo "Downloading font $family $FONTSOURCE_VERSION..."
    package_url="https://cdn.jsdelivr.net/npm/@fontsource-variable/$family@$FONTSOURCE_VERSION"
    curl -fsSL -o "$FONT_DIR/$family-latin-wght-normal.woff2" \
        "$package_url/files/$family-latin-wght-normal.woff2"
    curl -fsSL -o "$FONT_DIR/$family-LICENSE.txt" "$package_url/LICENSE"
done

echo ""
echo "Vendored assets rebuilt. Keep the versions in"
echo "src/vcpkg_harbor/dashboard/urls.py in sync when bumping them."
ls -l "$VENDOR_DIR" "$FONT_DIR"
