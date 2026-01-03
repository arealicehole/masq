# ============================================
# Image Processing Service - Phase 1 (CPU)
# Multi-stage build for minimal image size
# ============================================

# ============================================
# STAGE 1: Builder
# ============================================
FROM python:3.12-slim-bookworm AS builder

# Install build dependencies for Pillow and rembg
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libjpeg-dev \
    zlib1g-dev \
    libpng-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libwebp-dev \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Optional: Install Pillow-SIMD for 4-6x faster Lanczos
# Uncomment if your CPU supports AVX2 (most modern CPUs do)
# RUN pip uninstall -y pillow && \
#     CC="cc -mavx2" pip install --no-cache-dir pillow-simd

# Pre-download rembg models during build
RUN python -c "from rembg import new_session; new_session('birefnet-general'); new_session('isnet-general-use')"

# ============================================
# STAGE 2: Runtime
# ============================================
FROM python:3.12-slim-bookworm

# Install only runtime libraries (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo \
    zlib1g \
    libpng16-16 \
    libfreetype6 \
    liblcms2-2 \
    libwebp7 \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy pre-downloaded rembg models
COPY --from=builder /root/.u2net /root/.u2net

# Create non-root user for security
RUN useradd -m -u 1000 appuser

# Set working directory
WORKDIR /app

# Copy application code
COPY --chown=appuser:appuser . /app

# Create temp directory
RUN mkdir -p /tmp/img-proc && chown appuser:appuser /tmp/img-proc

# Switch to non-root user
USER appuser

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TEMP_DIR=/tmp/img-proc

# Expose FastAPI port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health', timeout=5).raise_for_status()"

# Run FastAPI with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
