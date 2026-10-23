# syntax=docker/dockerfile:1.7
# Ops image for Cloud Run jobs: migrations, seeding, demo reset, re-indexing.
# The core image installs igs-common non-editable and ships neither alembic.ini, migrations
# nor fixtures, so jobs run from this image, which keeps the package tree in place.
#   docker build -f scripts/deploy/ops.Dockerfile -t igs-ops .
ARG PYTHON_IMAGE=python:3.13-slim-bookworm

FROM ghcr.io/astral-sh/uv:0.12.21 AS uv

FROM ${PYTHON_IMAGE}
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/py-common/pyproject.toml packages/py-common/pyproject.toml
COPY services/core/pyproject.toml services/core/pyproject.toml
COPY services/worker/pyproject.toml services/worker/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package igs-core --no-install-workspace
COPY packages/py-common packages/py-common
# The seed publishes the example flows (and the executions parked on them).
COPY packages/flow-schema/examples packages/flow-schema/examples
COPY services/core services/core
# Editable install: igs_common.seed resolves fixtures/ relative to the package tree.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package igs-core \
    && useradd --system --uid 10001 --no-create-home igs
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER 10001
WORKDIR /app/packages/py-common
# Default job: migrate. Override the command for seed/reset/index (see docs/infra/runbook.md).
CMD ["alembic", "upgrade", "head"]
