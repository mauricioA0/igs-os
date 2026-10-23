# IGS OS — local development. Run `make help` for the list.
SHELL := /bin/bash
.DEFAULT_GOAL := help

DATABASE_URL ?= postgresql+asyncpg://igs:igs@localhost:5433/igs
TEMPORAL_ADDRESS ?= localhost:7233
TEMPORAL_NAMESPACE ?= igs
export DATABASE_URL TEMPORAL_ADDRESS TEMPORAL_NAMESPACE

ALEMBIC := uv run alembic -c packages/py-common/alembic.ini

.PHONY: help up down migrate seed api worker web test lint typecheck evals evals-full fmt

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

up: ## Start Postgres + Temporal (UI on http://localhost:8233)
	docker compose up -d --wait

down: ## Stop the local stack (data volumes are kept)
	docker compose down

migrate: ## Apply database migrations
	$(ALEMBIC) upgrade head

seed: ## Load the demo tenant (idempotent)
	uv run python -m igs_common.seed

api: ## Run the core API on :8000 with reload
	uv run uvicorn igs_core.app:create_app --factory --reload --port 8000

worker: ## Run the Temporal worker
	uv run python -m igs_worker

web: ## Run the Next.js app on :3000
	pnpm dev

test: ## Python tests
	uv run pytest

lint: ## Ruff + ESLint
	uv run ruff check .
	uv run ruff format --check .
	pnpm lint

fmt: ## Format Python
	uv run ruff format .
	uv run ruff check --fix .

typecheck: ## Pyright + tsc
	uv run pyright
	pnpm typecheck

evals: ## Evals, dry: no network, scripted agent + lexical baseline (what CI runs)
	uv run python -m evals.run --dry

evals-full: ## Evals against real models (paid: needs OPENAI_API_KEY; ARGS="--suite agent ...")
	uv run --env-file .env.local python -m evals.run --allow-paid $(ARGS)
