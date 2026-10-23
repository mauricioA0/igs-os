# syntax=docker/dockerfile:1.7
# CPU image for the IGS OS models service (BGE-M3 embeddings + bge-reranker-v2-m3).
# Build from services/models:  docker build -t igs-models .
# Weights are fetched at a pinned revision, checksum-verified and converted to safetensors in the
# `weights` stage; the runtime image only contains safetensors + tokenizer files.

FROM python:3.13-slim AS deps
COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project
COPY src ./src
COPY scripts ./scripts
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev

FROM deps AS weights
# Cache mount: rebuilds don't re-download ~4.5 GB of upstream weights.
RUN --mount=type=cache,target=/root/.cache/huggingface \
    /app/.venv/bin/python scripts/prepare_models.py --out /models

FROM python:3.13-slim AS runtime
RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app app
WORKDIR /app
COPY --from=deps /app/.venv /app/.venv
COPY --from=deps /app/src /app/src
COPY --from=weights --chown=app:app /models /models
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    HF_HUB_OFFLINE=1 \
    IGS_MODELS_DIR=/models \
    IGS_MODELS_DEVICE=cpu
USER app
EXPOSE 8080
# One process: both models stay resident (~4.5 GB RAM). Scale with instances, not workers.
CMD ["uvicorn", "igs_models.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
