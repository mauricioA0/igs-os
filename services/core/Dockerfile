# syntax=docker/dockerfile:1.7
# Build from the repo root:  docker build -f services/core/Dockerfile -t igs-core .

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
    uv sync --frozen --no-dev --package igs-core --no-install-workspace
# Then the code.
COPY packages/py-common packages/py-common
COPY services/core services/core
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package igs-core --no-editable

FROM ${PYTHON_IMAGE} AS runtime
RUN useradd --system --uid 10001 --no-create-home igs
COPY --from=build --chown=igs:igs /app/.venv /app/.venv
# The LLM price table lives outside the installed package (non-editable install).
COPY --chown=igs:igs packages/py-common/pricing /app/pricing
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 IGS_LOG_JSON=true PORT=8080 \
    IGS_LLM_PRICES_FILE=/app/pricing/models.yaml
USER 10001
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn --factory igs_core.app:create_app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*' --no-server-header --no-access-log"]
