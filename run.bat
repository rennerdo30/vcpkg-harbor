@echo off
REM Quick start script for vcpkg-harbor (Windows)

if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
    call .venv\Scripts\activate
    pip install -e .
) else (
    call .venv\Scripts\activate
)

REM Create directories
if not exist logs mkdir logs
if not exist cache mkdir cache

REM Set defaults for local filesystem storage
if not defined VCPKG_STORAGE_TYPE set VCPKG_STORAGE_TYPE=filesystem
if not defined VCPKG_STORAGE_PATH set VCPKG_STORAGE_PATH=./cache

echo Starting vcpkg-harbor...
vcpkg-harbor
