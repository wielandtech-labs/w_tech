# Multi-stage build:
# - builder: compiles deps (libpq-dev, build-essential) + caches pip downloads
# - runtime: slim image with only runtime lib (libpq5), no build toolchain

# --- stage 1: build/install dependencies ---
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_COMPILE=1

# Build-time system deps (not copied to runtime)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev

# Install Python deps into an isolated venv; pip download cache persists on the
# buildkitd PVC so wheels are not re-fetched when only source files change.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && pip install -r requirements.txt


# --- test stage: run the Django test suite (CI builds it with `target: test`) ---
# Not part of the runtime image: buildkit only builds stages the requested
# target depends on. The runner has no Docker daemon or service containers, so
# tests run here against sqlite; Postgres-only tests skip themselves.
FROM builder AS test
WORKDIR /wielandtech
COPY . .
RUN DATABASE_ENGINE=sqlite \
    DJANGO_SECRET_KEY=build-only-not-a-secret \
    RECAPTCHA_PUBLIC_KEY=dummy \
    RECAPTCHA_PRIVATE_KEY=dummy \
    python manage.py test --noinput -v 2


# --- stage 2: runtime image ---
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Only the runtime shared library (libpq5), not the dev headers
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy the venv from the builder stage (no build toolchain in the final image)
COPY --from=builder /opt/venv /opt/venv

WORKDIR /wielandtech
COPY . .

# Fail the build if any model change lacks a committed migration, making the
# committed migrations the single source of truth for the schema. This lets the
# runtime start with `migrate` alone, without a `makemigrations` fallback that
# would silently auto-generate (and apply) unreviewed migrations in-cluster.
# --check needs no database; the sqlite/dummy env just lets settings import.
RUN DATABASE_ENGINE=sqlite \
    DJANGO_SECRET_KEY=build-only-not-a-secret \
    RECAPTCHA_PUBLIC_KEY=dummy \
    RECAPTCHA_PRIVATE_KEY=dummy \
    python manage.py makemigrations --check --dry-run

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "wielandtech.wsgi:application"]
