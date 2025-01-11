#!/usr/bin/env bash

# Exit on error
set -e

# Default values
MODE="development"
STORAGE_TYPE="file"
STORAGE_PATH="./cache"
PORT="15151"
HOST="0.0.0.0"
LOG_LEVEL="INFO"
WORKERS="4"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Show help function
show_help() {
    echo "Usage: ./run.sh [options]"
    echo
    echo "Options:"
    echo "  --help          Show this help message"
    echo "  --prod          Run in production mode"
    echo "  --dev           Run in development mode (default)"
    echo "  --port <port>   Set port number (default: 15151)"
    echo "  --host <host>   Set host address (default: 0.0.0.0)"
    echo "  --storage <type> Set storage type (file/minio)"
    echo "  --path <path>   Set storage path for file storage"
    echo "  --log-level <level> Set log level (DEBUG/INFO/WARNING/ERROR)"
    echo "  --workers <num> Set number of workers (default: 4)"
    echo "  --docker        Run using Docker"
    echo "  --docker-dev    Run using Docker in development mode"
    echo
    echo "Examples:"
    echo "  ./run.sh --dev --port 8080"
    echo "  ./run.sh --prod --storage minio"
    echo "  ./run.sh --docker"
    exit 0
}

# Log functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check dependencies
check_dependencies() {
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is not installed"
        exit 1
    fi
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --help)
            show_help
            ;;
        --prod)
            MODE="production"
            shift
            ;;
        --dev)
            MODE="development"
            shift
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --host)
            HOST="$2"
            shift 2
            ;;
        --storage)
            STORAGE_TYPE="$2"
            shift 2
            ;;
        --path)
            STORAGE_PATH="$2"
            shift 2
            ;;
        --log-level)
            LOG_LEVEL="$2"
            shift 2
            ;;
        --workers)
            WORKERS="$2"
            shift 2
            ;;
        --docker)
            log_info "Starting vcpkg-harbor using Docker..."
            docker compose up -d
            exit 0
            ;;
        --docker-dev)
            log_info "Starting vcpkg-harbor using Docker in development mode..."
            docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
            exit 0
            ;;
        *)
            log_error "Unknown parameter: $1"
            show_help
            ;;
    esac
done

# Check dependencies
check_dependencies

# Create virtual environment if it doesn't exist
if [[ ! -d ".venv" ]]; then
    log_info "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate

# Install requirements if needed
if [[ ! -f ".venv/bin/uvicorn" ]]; then
    log_info "Installing requirements..."
    pip install -r requirements.txt
fi

# Create necessary directories
mkdir -p "${STORAGE_PATH}"
mkdir -p logs

# Set environment variables
export VCPKG_HOST="${HOST}"
export VCPKG_PORT="${PORT}"
export VCPKG_STORAGE_TYPE="${STORAGE_TYPE}"
export VCPKG_STORAGE_PATH="${STORAGE_PATH}"
export VCPKG_LOG_LEVEL="${LOG_LEVEL}"
export VCPKG_WORKERS="${WORKERS}"

# Print configuration
log_info "Configuration:"
log_info "  Mode: ${MODE}"
log_info "  Host: ${HOST}"
log_info "  Port: ${PORT}"
log_info "  Storage: ${STORAGE_TYPE}"
log_info "  Storage Path: ${STORAGE_PATH}"
log_info "  Log Level: ${LOG_LEVEL}"
log_info "  Workers: ${WORKERS}"

# Run the application
if [[ "${MODE}" == "development" ]]; then
    log_info "Starting vcpkg-harbor in development mode..."
    python -m uvicorn main:app \
        --host "${HOST}" \
        --port "${PORT}" \
        --reload \
        --log-level debug
else
    log_info "Starting vcpkg-harbor in production mode..."
    python main.py
fi