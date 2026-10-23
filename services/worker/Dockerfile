# syntax=docker/dockerfile:1.7
# Temporal worker. Build from the repo root:
#   docker build -f services/worker/Dockerfile -t igs-worker .
# Runs one or more task queues: `docker run igs-worker --queue flows` (default: all queues).

ARG PYTHON_IMAGE=python:3.13-slim-bookworm

FROM ghcr.io/astral-sh/uv:0.12.21 AS uv

FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependency layer first (cached unless the lockfile or manifests change).
COPY pyproject.toml uv.lock ./
COPY packages/py-common/pyproject.toml packages/py-common/pyproject.toml
COPY services/core/pyproject.toml services/core/pyproject.toml
COPY services/worker/pyproject.toml services/worker/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package igs-worker --no-install-workspace
# Then the code.
COPY packages/py-common packages/py-common
COPY services/worker services/worker
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package igs-worker --no-editable

FROM ${PYTHON_IMAGE} AS runtime
RUN useradd --system --uid 10001 --no-create-home igs
COPY --from=build --chown=igs:igs /app/.venv /app/.venv
# Reviewed price table for per-call cost (igs_common.llm). It lives outside the wheel, so the
# default path doesn't resolve in a non-editable install; point the setting at the copy.
COPY --chown=igs:igs packages/py-common/pricing /app/pricing
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    IGS_LLM_PRICES_FILE=/app/pricing/models.yaml
USER 10001
# Workers only long-poll Temporal: nothing to expose. SIGTERM drains in-flight tasks.
ENTRYPOINT ["python", "-m", "igs_worker"]
