# ==============================================================================
# Job Copilot - Production Dockerfile
# ==============================================================================

FROM python:3.13-slim-bookworm AS base

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    PORT=8000 \
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
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged application user
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -s /bin/bash -m appuser

# Set working directory
WORKDIR /app

# Copy dependency definition
COPY pyproject.toml README.md ./

# Install application dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Install Playwright Chromium browser binaries
RUN mkdir -p /ms-playwright && \
    playwright install chromium && \
    chown -R appuser:appgroup /ms-playwright

# Copy application source code and safe repository configs
COPY src/ ./src/
COPY data/config/ ./data/config/
COPY data/resume_strategies/ ./data/resume_strategies/
COPY data/sample_jds/ ./data/sample_jds/

# Create runtime directories with appropriate permissions
RUN mkdir -p /app/data/candidate /app/data/jobs /app/data/applications /app/data/tracking /app/data/copilot /app/data/downloads && \
    chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Expose API port
EXPOSE 8000

# Container Healthcheck against /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Default execution: run the FastAPI web server
CMD ["uvicorn", "job_copilot.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
