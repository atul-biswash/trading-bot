# syntax=docker/dockerfile:1

# ---- Stage 1: build wheels for all dependencies -----------------------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Build tooling needed by some scientific wheels.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel --wheel-dir=/wheels -r requirements.txt

# ---- Stage 2: slim runtime image -------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Run as a non-root user.
RUN useradd --create-home --uid 1000 appuser
WORKDIR /app

# Install pre-built wheels (no compiler needed in the final image).
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

# Application code.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-deps -e .

# Writable runtime dirs (also mounted as volumes in docker-compose).
RUN mkdir -p /app/data/historical /app/logs \
    && chown -R appuser:appuser /app
USER appuser

# config.yaml and .env are provided at runtime via volume / env_file.
CMD ["python", "-m", "trading_bot", "run"]
