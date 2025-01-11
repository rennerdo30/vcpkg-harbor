FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .
COPY .env .

# Create logs directory
RUN mkdir -p logs

# Create non-root user
RUN useradd -m -u 1000 vcpkg
RUN chown -R vcpkg:vcpkg /app
USER vcpkg

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${VCPKG_PORT:-15151}/health || exit 1

# Run the application
CMD ["python", "main.py"]