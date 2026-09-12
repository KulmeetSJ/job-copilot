# ==============================================================================
# Job Copilot - Production Dockerfile
# ==============================================================================

FROM python:3.13-slim-bookworm AS base

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    PORT=8000 \
    PYTHONPATH=/app/src \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Install required system dependencies for Playwright Chromium and networking
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && curl -fsSL "https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.15.0/tectonic-0.15.0-x86_64-unknown-linux-musl.tar.gz" | tar -xz -C /usr/local/bin \
    && chmod +x /usr/local/bin/tectonic \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged application user
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -s /bin/bash -m appuser

# Set working directory
WORKDIR /app

# Copy dependency definition and source code
COPY pyproject.toml README.md alembic.ini ./
COPY src/ ./src/
COPY data/candidate/ ./data/candidate/
COPY data/config/ ./data/config/
COPY data/resume_strategies/ ./data/resume_strategies/
COPY data/sample_jds/ ./data/sample_jds/

# Install application and dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e .

# Install Playwright Chromium browser binaries
RUN mkdir -p /ms-playwright && \
    playwright install chromium && \
    chown -R appuser:appgroup /ms-playwright

# Create runtime directories with appropriate permissions
RUN mkdir -p /app/data/candidate /app/data/jobs /app/data/applications /app/data/tracking /app/data/copilot /app/data/downloads && \
    chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Expose API port
EXPOSE 8000

# Container Healthcheck against /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, os; port = os.environ.get('PORT', '8000'); urllib.request.urlopen(f'http://localhost:{port}/health')" || exit 1

# Default execution: run the FastAPI web server respecting cloud PORT environment variable
CMD ["sh", "-c", "uvicorn job_copilot.api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
