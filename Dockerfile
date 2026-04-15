# ══════════════════════════════════════════════════════════════════════════════
# n8n Unified MCP Server — Production Dockerfile
# Multi-stage build for minimal, secure image
# ══════════════════════════════════════════════════════════════════════════════

# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Production Image ─────────────────────────────────────────────────
FROM python:3.12-slim AS production

# Security: run as non-root user
RUN groupadd -r mcpuser && useradd -r -g mcpuser mcpuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY --chown=mcpuser:mcpuser . .

# Remove dev files from image
RUN rm -f .env.example .env && \
    find . -name "*.pyc" -delete && \
    find . -name "__pycache__" -delete

# Switch to non-root user
USER mcpuser

# Expose MCP server port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Production start command
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--loop", "uvloop", \
     "--no-access-log"]
