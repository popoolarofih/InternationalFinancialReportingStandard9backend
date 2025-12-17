# Builder stage: build wheels to avoid compiling in final image
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install build dependencies for packages like psycopg2, cryptography, etc.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential gcc libpq-dev curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and build wheels
COPY requirements.txt ./
RUN python -m pip install --upgrade pip setuptools wheel \
    && mkdir /wheels \
    && pip wheel --wheel-dir=/wheels -r requirements.txt

# Final stage: minimal runtime image
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create non-root user
RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /app

# Copy wheels and install from wheels to avoid build tools in runtime
COPY --from=builder /wheels /wheels
COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && pip install --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels ~/.cache/pip

# Copy application source
COPY . .

# Ensure correct ownership
RUN chown -R app:app /app

USER app

EXPOSE 8000

# Minimal healthcheck (optional)
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import socket; s=socket.socket(); s.settimeout(2); \
  (s.connect(('127.0.0.1',8000)), s.close()) if True else exit(1)" || exit 1
# Ensure necessary directories exist
RUN mkdir -p /app/worktemplates

# Default command (override in docker-compose / docker run as needed)
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]