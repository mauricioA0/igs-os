# Phase 1 contracts — module ownership

Supersedes the TypeScript-era contracts (git history). Read with `docs/architecture/data-model.md` and `core-api.md`.

## Ground rules for every agent

- Python 3.13, uv workspace at the repo root. Run everything with `uv run …` from the root. **Do not run `uv add`, `uv lock` or `uv sync`** — dependencies are pre-installed (list below). If you need another one, say so in your report.
- Web: pnpm workspace, app in `apps/web`. Don't run `pnpm add`.
- Local Postgres: `docker compose up -d db` → `postgres://igs:igs@localhost:5433/igs` (pgvector image). Use a separate database per test session (`igs_test_<agent>`) so agents don't collide.
- Only write the paths you own. Don't commit. Don't touch GCP.
- LLM provider is **OpenAI** (`openai` SDK 3.x installed — read its installed source/types before writing code; model ids come from config, never hardcoded). No key is available yet: tests use fakes.
- Style: ruff (line 100), type hints everywhere, pyright-clean, pytest with `asyncio_mode=auto`.

Installed: sqlalchemy[asyncio] 2, asyncpg, alembic, pydantic 2, pydantic-settings, openai 3.x, cel-python, cryptography, pyyaml, structlog, opentelemetry-api (igs-common); fastapi, uvicorn, mcp, httpx, sse-starlette (igs-core); temporalio 1.34 (igs-worker); pytest, pytest-asyncio, ruff, pyright, datamodel-code-generator (dev).

## Packages and owners

| Path | Owner | Exposes |
|---|---|---|
| `packages/py-common/src/igs_common/db/**`, `packages/py-common/migrations/**`, `packages/py-common/alembic.ini` | **P1** | SQLAlchemy models (all tables in data-model.md **plus Account 360**: `accounts`, `stakeholders`, `interactions`, `account_facts`), `db.session`: `create_engine(url)`, `session_scope(tenant_id)` (async ctx manager that runs `SET LOCAL app.tenant_id`), RLS policies in migrations |
| `packages/py-common/src/igs_common/domain/**` | **P2** | Pure logic, no I/O: `planner.plan_itinerary(...)`, `pricing.quote(...)`, `approvals.payload_hash(...)`, `tools.ToolClass`, status transition rules |
| `packages/py-common/src/igs_common/seed/**`, `packages/py-common/fixtures/**` | **P3** | Demo tenant fixtures as YAML (catalog, trips/leads matching the web prototype mocks, **6 client accounts with stakeholders, emails, call notes, chat transcripts** for Account 360) + `seed.load(session)` idempotent upsert |
| `services/core/**` | **P4** | FastAPI app factory `igs_core.app:create_app()`, settings, tenant/demo middleware, error model, `/healthz`, `/v1` router skeleton, OpenAPI export script |
| `docker-compose.yml`, `Makefile`, `.github/workflows/**`, `.pre-commit-config.yaml` | **P5** | Local stack (Postgres+pgvector, Temporal dev server + UI), dev commands, CI |
| `packages/py-common/src/igs_common/llm/**` | **P6** | `LLMClient` protocol, OpenAI implementation (structured outputs, tool calling, streaming), model registry from settings, `FakeLLM` for tests, usage/cost capture |
| `packages/py-common/src/igs_common/flows/**`, `packages/flow-schema/**`, `apps/web/src/lib/flow-schema.ts` | **P7** | Pydantic models generated from `flow.schema.json`, CEL evaluator with helpers, publish-time validator (graph + security rules) |
| `services/worker/**` | **P8** | Temporal worker bootstrap, flow interpreter workflow skeleton (from `spikes/temporal`), payload codec, replay test harness |
| `docs/design/account-360.md`, `apps/web/src/app/(prototype)/ops/accounts/**` | **P9** | Account 360 spec + clickable prototype |
| `docs/PLAN.md`, `docs/README.md` | **P10** | Plan v3 consolidating every review |

## Account 360 — shared shape (P1 models, P3 fixtures, P9 spec must agree)

- `accounts`: id, tenant_id, name, kind (`university` \| `club` \| `high_school` \| `family_group`), country, state/city, sport programs, tier, owner_user_id, status (`prospect` \| `active` \| `past` \| `churned`), health (`green` \| `amber` \| `red`), created_at.
- `stakeholders`: id, account_id, name, title, role (`decision_maker` \| `champion` \| `coach` \| `assistant_coach` \| `athletic_director` \| `compliance` \| `travel_coordinator` \| `finance` \| `parent_liaison` \| `other`), influence (1–5), sentiment (`positive` \| `neutral` \| `negative` \| `unknown`), email, phone, preferred_channel, last_contact_at, notes. **No minors.**
- `interactions`: id, account_id, stakeholder_id?, channel (`email` \| `call` \| `meeting` \| `chat` \| `whatsapp` \| `note`), direction, occurred_at, subject, body (source text; chunked + embedded for RAG), trip_id?, lead_id?.
- `account_facts`: id, account_id, kind (`status` \| `commitment` \| `risk` \| `preference` \| `budget` \| `decision`), statement, confidence, source_interaction_id, valid_from, superseded_by? — extracted by the LLM with provenance, never without a source.

---

# Wave 2 contracts — phases 2 (RAG + Account 360) and 3 (agent + MCP + API)

Same ground rules as phase 1. Newly installed: pgvector (py), google-cloud-vectorsearch 0.11.5 (beta), pypdf, python-docx (igs-common); opentelemetry-sdk (igs-worker). **`.env.local` holds a real `OPENAI_API_KEY` — do NOT make paid calls**; use `FakeLLM`. Model roles → ids live in `IGS_LLM_MODELS` (agent, chat, extractor, judge, simulator, reasoning, fast); prices in `packages/py-common/pricing/models.yaml`.

| Path | Owner | Exposes |
|---|---|---|
| `packages/py-common/src/igs_common/rag/**` | **W1** | `VectorStore` protocol + `PgVectorStore` (default; HNSW + Postgres FTS, RRF fusion) + `VertexVectorStore` (adapter, unit-tested with fakes); `Embedder`/`Reranker` protocols + HTTP clients to the models service + `HashEmbedder` fake; `retrieve(query, tenant_id, filters, k)` → hits with citations. Tenant filter always injected server-side |
| `services/models/**` (own uv project, NOT a workspace member) | **W2** | FastAPI: `POST /embed` (BGE-M3 dense+sparse), `POST /rerank` (bge-reranker-v2-m3), CPU locally, Dockerfile (CPU) + vLLM GPU notes |
| `services/worker/src/igs_worker/workflows/ingestion.py`, `.../activities/ingestion*.py`, `packages/py-common/src/igs_common/ingest/**` | **W3** | Parse (pdf/docx/html/text/interactions) → structure-aware chunks → embed → upsert; content-hash idempotency; quarantine heuristics for injected instructions |
| `packages/py-common/src/igs_common/accounts/**`, `services/core/src/igs_core/api/v1/accounts_ai.py` | **W4** | Fact extraction (verbatim-quote verified), deterministic health rules, brief generation with citations + cache by inputs_hash, `ask(account, question)` RAG answer; routes `GET /v1/accounts/{id}/brief`, `POST /v1/accounts/{id}/ask` |
| `packages/py-common/migrations/versions/0002_*.py` + matching model edits + `igs_common/seed/**` updates | **W5** | Gaps: approvals.subject_type/subject_id, trips.travelers/owner_user_id, trip_items.alert/time, account_facts.severity/due_date/status, `account_briefs` table, documents content location, SECURITY DEFINER fn for API-key lookup; seed uses new columns |
| `services/worker/**` except W3 paths | **W6** | Use `igs_common.flows` (cel/schema) instead of local copies; implement say/capture/choice/map; agent + knowledge_search + domain action activities wired to `igs_common.llm` / `rag` / domain; add `fast`/`reasoning` roles to `igs_common.llm.types.Role` if missing (only that edit in llm/) |
| `evals/**` (uv project or workspace-free scripts), `.github/workflows/evals.yml` | **W7** | Retrieval evals (golden from fixtures/account-qa.yaml + knowledge Q&A), embeddings comparison runner, agent eval harness (simulated ops + coach personas, judge with structured output, thresholds), `--dry` with FakeLLM, nightly workflow |
| `services/core/src/igs_core/agent/**`, `services/core/src/igs_core/mcp/**` | **W8** | Copilot runtime (tool loop via `igs_common.llm.tools`, tool registry with ToolClass policy from `igs_common.domain.tools`, approvals instead of external writes, SSE events), MCP server (streamable HTTP, mountable ASGI app) exposing the core-api.md tool catalog; report the mount line for `app.py` |
| `services/core/src/igs_core/api/v1/{approvals,flows,executions,events}.py`, `services/core/src/igs_core/events/**`, `services/core/src/igs_core/app.py` | **W9** | Approvals list/decide (verify payload_hash, signal Temporal), flows CRUD (draft/If-Match/validate/publish), executions start/list/detail/SSE, outbox dispatcher → Temporal; mounts W4 and W8 routers |
| `docs/**` except CONTRACTS.md, `README.md` | **W10** | Keep docs truthful as code lands: update flow-engine.md (version as input, GKE workers), core-api.md (new routes), PLAN status; write README.md (what/why/architecture/quickstart/how built with AI) |

---

# Wave 3 contracts — web on the real API + UX proposals #1–#4, #6

Read `docs/architecture/frontend.md` (containers/presentational, controlled+uncontrolled, HOCs, scoped Zustand) and `docs/reviews/ux/README.md`. Web runs on Node 24 (`PATH=$HOME/.nvm/versions/node/v24.13.0/bin:$PATH`). Installed: openapi-fetch, openapi-typescript, @playwright/test, @axe-core/playwright, vitest, @testing-library/react, jsdom, zustand, @xyflow/react, lucide-react. Typed API types: `apps/web/src/lib/api/schema.d.ts` (regenerate with `npx openapi-typescript openapi.json -o src/lib/api/schema.d.ts` after core changes). Local API: `uv run uvicorn igs_core.app:create_app --factory --port 8000` with `DATABASE_URL=postgres://igs:igs@localhost:5433/igs` (seeded, demo tenant slug `igs`, no login). No paid OpenAI calls. Decisions: Lakeshore health is **red** (overdue balance, departs soon) and the demo story is built around resolving it; the demo copilot may **propose** approvals, never approve.

| Path | Owner | Delivers |
|---|---|---|
| `apps/web/src/lib/api/**` (except schema.d.ts), `apps/web/src/components/hoc/**`, `apps/web/src/components/ui/use-controllable-state.ts`, `apps/web/src/features/_shared/**` | **X1** | Typed client (openapi-fetch) for server and client, `API_URL` env, problem+json errors, SSE helper; HOCs from frontend.md; `useControllableState` + migrate ui primitives to it; vitest setup |
| `apps/web/src/app/globals.css`, `apps/web/src/components/ui/**` (except X1's hook), `apps/web/src/app/layout.tsx`, `apps/web/src/app/design/**` | **X2** | UX #3: OKLCH scales from 3 base values, 11px min type, single Badge, contrast fixes, per-surface `lang` (es for ops, en for coach), dark mode everywhere; then remove private palettes (`flows.css`, proposal/chat arbitrary colors) by giving owners token equivalents — coordinate via report |
| `apps/web/src/features/{trips,leads,accounts,today}/**`, `apps/web/src/app/(app)/ops/**` routes for those (move from `(prototype)`), ops layout/shell | **X3** | Ops panel on the real API (trips, items actions, leads, accounts list/detail with brief + ask), citation chips (UX #2 part), hydration fix, ops shell with sidebar + mobile bottom bar; mounts `<CopilotDrawer/>` from X5 and approvals nav from X4 |
| `apps/web/src/features/approvals/**`, `apps/web/src/app/(app)/ops/approvals/**` | **X4** | UX #4: approvals inbox on `/v1/approvals`: real preview of what will be sent, payload-hash decide, edit-and-approve with diff, J/K/A/R/E shortcuts, waits in destination local time |
| `apps/web/src/features/copilot/**` | **X5** | UX #2: `<CopilotDrawer/>` (⌘J), Zustand store per instance, SSE `/v1/copilot/turns`, pre-loaded Lakeshore question, streamed tool steps, citation chips, approval cards, context chips |
| `apps/web/src/features/flows/**`, `apps/web/src/app/(app)/ops/flows/**` (move from `(prototype)/flows`) | **X6** | Flow editor + executions on `/v1/flows` and `/v1/executions` (If-Match draft, validate problems on canvas, publish, start test run, SSE execution viewer), inside the ops shell, Spanish, tokens only |
| `services/core/src/igs_core/api/v1/public_chat.py`, `apps/web/src/features/coach/**`, `apps/web/src/app/(public)/**` (chat + proposal, move from `(prototype)`) | **X7** | Public coach chat on the real inbound-inquiry flow (start execution, `user_message` signal, stream outbox messages) + UX #6 proposal (package price, Reserve CTA → deposit approval, dark photographic look with licensed placeholders, PDF ≤ 5 pages) |
| `packages/py-common/fixtures/**`, `packages/py-common/src/igs_common/seed/**`, `apps/web/src/features/tour/**`, `apps/web/src/app/page.tsx` | **X8** | UX #1: one coherent Lakeshore story across every surface (March 2027 inquiry, red health, pending approval, linked execution), seed `flow_triggers`, demo reset command; guided "Start the 2-minute tour" with step rail; landing CTA |
| `apps/web/e2e/**`, `apps/web/playwright.config.ts`, `.github/workflows/e2e.yml` | **X9** | Playwright e2e for the demo story + axe checks per page; CI job that boots Postgres+API+web |
| `services/worker/**`, `packages/py-common/src/igs_common/{codec,temporal}/**`, `packages/py-common/migrations/versions/0004_*.py`, `services/core/src/igs_core/{config.py,temporal.py}` | **X10** | Backend gaps: move payload codec to igs_common and use it in core's Temporal client; align Temporal namespace (`igs`); migration 0004 NOTIFY trigger on flow_node_runs; demo principal can propose approvals in copilot (never approve); script to mint an MCP API key for the demo |

`(prototype)` routes are deleted by their new owners once moved. Shared layout files between X3/X4/X5/X6: X3 owns the shell and imports the others' exports; report anything X3 must mount.

---

# Wave 4 contracts — infra as code, remaining gaps, delivery

Same ground rules. **Nothing is applied to GCP**: write Terraform/Helm/pipelines and validate them offline (`docker run hashicorp/terraform:1.9 …` for `fmt`/`validate`/`init -backend=false`, `docker run alpine/helm` for `lint`/`template`). Project `mv-cloud-509914`, region `us-central1`, gcloud account `<owner-account>` (read-only gcloud allowed). Demo mode first (low idle cost, pgvector as vector store, models on CPU Cloud Run, Temporal on GKE Autopilot with Spot), prod mode as a variable.

| Path | Owner | Delivers |
|---|---|---|
| `infra/terraform/**` | **Y1** | Modules + `envs/demo` & `envs/prod`: VPC + private service access, Cloud SQL app + Temporal (private IP, IAM auth), Artifact Registry, Secret Manager secrets (names only), service accounts + least-privilege IAM, Cloud Run (core API, models CPU, optional GPU), GKE Autopilot (Temporal + workers), Workload Identity Federation for GitHub Actions, budget + alert, optional Vertex Vector Search collection behind a flag; remote state bucket bootstrap; outputs; `terraform validate` clean |
| `infra/helm/**`, `infra/k8s/**`, `services/worker/Dockerfile` | **Y2** | Temporal Helm values (chart 1.x, postgres12_pgx, SQL visibility, 512 shards, no ES, Autopilot-safe), schema Job, worker Deployments per queue + KEDA ScaledObjects (Temporal scaler), Temporal UI behind IAP (BackendConfig/Ingress), NetworkPolicies; worker Dockerfile; `helm lint/template` clean |
| `.github/workflows/deploy.yml`, `docs/infra/runbook.md`, `scripts/deploy/**` | **Y3** | CD with WIF: build/push images (core, worker, models), run migrations as a job, deploy Cloud Run, helm upgrade, Vercel deploy step (token secret), smoke checks; manual approval gate on prod; runbook (bootstrap, deploy, rollback, rotate codec key, pause/resume demo to cut idle cost) |
| `services/core/src/igs_core/api/v1/{trips,leads}.py`, `services/core/src/igs_core/repositories/**`, `services/core/src/igs_core/schemas/**` | **Y4** | `PATCH /v1/trips/{id}/items/{item_id}` (status transitions via domain, audit, outbox events; demo read-only), `GET/PATCH /v1/leads` (list/detail/status), richer trip items (time, alert, opponent name+level, provider name), interaction excerpt in account detail; tests; regenerate `apps/web/openapi.json` + `schema.d.ts` |
| `apps/web/src/features/{trips,leads,today,accounts,ops-shell}/**` | **Y5** | Use Y4's endpoints (item actions, leads kanban on real data, richer items, citation previews with excerpt), sidebar badge = `effectiveStatus` count, remove remaining private styles/arbitrary values in those features |
| `packages/py-common/src/igs_common/seed/**` (reset only), `services/core/scripts/demo_reset.py`, `loadtest/**` | **Y6** | Demo reset also starts a real Temporal workflow parked at `ops_review` for the seeded execution (approve resumes it); k6 + mock-LLM load test per docs/architecture/cost-and-scale.md with a results template |
| `docs/delivery/**`, `README.md` | **Y7** | Final README with real numbers, 2-minute video script + shot list |
| `docs/reviews/security-2026-10.md` | **Y8** | Security review of the code as it is (auth, RLS, public endpoints, MCP, approvals, prompt-injection containment, secrets, supply chain) with severity, file:line and fixes; implement only trivial fixes in files nobody else owns this wave, list the rest |
