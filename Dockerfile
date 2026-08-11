# =============================================================================
# EduStream AI — Production Dockerfile
# =============================================================================
# Multi-stage NOT needed (Python app, no build step).
# Security: runs as non-root user.
# Secrets: loaded from environment variables at runtime (never baked in).
# =============================================================================

FROM python:3.11-slim

LABEL maintainer="EduStream AI"
LABEL description="AI-powered educational content streaming service"

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Default port (can be overridden by App Runner via PORT env var)
ENV PORT=8000

WORKDIR /app

# Install system dependencies (curl for health check)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer caching)
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/

# Security: create and switch to a non-root user
RUN useradd --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose the application port
EXPOSE 8000

# Health check — App Runner also has its own health check configured
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/api/capabilities || exit 1

# Start the application
# GROQ_API_KEYS must be set as an environment variable at runtime — NEVER hardcode here
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
