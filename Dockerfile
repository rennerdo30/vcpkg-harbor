FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ src/

# Install the package
RUN pip install --no-cache-dir .

# Create logs directory
RUN mkdir -p logs

# Create non-root user
RUN useradd -m -u 1000 vcpkg
RUN chown -R vcpkg:vcpkg /app
USER vcpkg

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${VCPKG_SERVER_PORT:-15151}/health || exit 1

# Expose default port
EXPOSE 15151

# Run the application
CMD ["vcpkg-harbor"]
