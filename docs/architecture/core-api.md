# Core API (`services/core`)

Status: design, phase 1. Companion to [data-model.md](data-model.md) and [../PLAN.md](../PLAN.md).

## 1. Responsibilities and boundaries

`services/core` is a stateless FastAPI app on Cloud Run. It owns:

- the **REST API** consumed by `apps/web` (the web app never touches the database);
- the **MCP server** (Streamable HTTP, mounted at `/mcp`) for Claude Code / Desktop and other MCP clients;
- the **interactive agent runtime** (chat turns that stream to a user);
- **retrieval** (query side of RAG);
- **writes to Postgres** and the **outbox** of domain events.

It does **not** run long work. Anything that can outlive a request goes to Temporal and runs in `services/worker`: flow executions, ingestion, provider-confirmation fan-outs, scheduled triggers. Core *starts* workflows and *sends signals* (approval decisions, chat messages for `capture` nodes); it never waits on them beyond a request's lifetime.

| Concern | core | worker |
|---|---|---|
| HTTP / MCP / SSE | ✅ | — |
| Domain writes (repositories) | ✅ | ✅ (same `py-common` code, called from activities) |
| Agent turn streamed to a user | ✅ | — |
| Agent node inside a flow | — | ✅ (activity, non-streaming) |
| Retrieval query | ✅ | ✅ (via `py-common`) |
| Ingestion (parse/chunk/embed/upsert) | starts it | ✅ |
| Outbox dispatch | ✅ (background task) or a small dedicated Cloud Run job | — |

## 2. Repository layout

Matches PLAN.md §3, with module detail:

```
packages/py-common/igs_common/
  config.py            pydantic-settings; one Settings object per service
  db/                  engine/session factory, models.py, TenantScoped base, repositories/
  domain/              leads.py, trips.py (pure planItinerary port), pricing.py, approvals.py
  events/              event types (Pydantic), outbox writer
  retrieval/           Embedder protocol + qwen3/bge_m3/openai impls, Reranker, VectorStore (vertex, pgvector), search.py
  flows/               graph schema (Pydantic, generated from packages/flow-schema), expression engine, node registry
  agents/              tool definitions shared by MCP + agents, prompt builders
  telemetry.py         OpenTelemetry setup (Cloud Trace exporter)
services/core/igs_core/
  main.py              app factory, lifespan (engine, Temporal client, OTel)
  api/                 routers: auth, leads, trips, catalog, conversations, flows, executions, approvals, documents, search, traces, events, admin
  mcp/                 FastMCP server; tools = thin adapters over igs_common.agents
  agent/               streaming copilot runtime (OpenAI via `igs_common.llm`), tracing
  outbox/              dispatcher
  migrations/          Alembic
services/worker/igs_worker/
  main.py              Temporal worker bootstrap (task queues: flows, ingestion, agents)
  workflows/           FlowExecutionWorkflow, IngestDocumentWorkflow, ScheduleTickWorkflow
  activities/          node activities, ingestion activities
evals/                 retrieval/, agents/, flows/  (pytest-based, run in CI)
```

## 3. REST API

Base path `/v1`. JSON, snake_case. Auth: `Authorization: Bearer <token>` — either a user session token (OIDC ID token from Google sign-in, verified by core) or an API key (`igs_…`, hashed in `api_keys`). Tenant resolved from the principal; never from the request body. Errors use RFC 9457 problem+json. Lists use cursor pagination (`?cursor=&limit=`, max 200). Mutations accept `Idempotency-Key` (stored 24h).

| Resource | Endpoints | Notes |
|---|---|---|
| Auth | `GET /me` | principal, role, tenant |
| Accounts (Account 360) | `GET /accounts?health=&status=`, `GET /accounts/{id}` (stakeholders, current facts with `source_interaction_id`, last 20 interactions), `GET /accounts/{id}/brief` (cached brief with citations), `POST /accounts/{id}/ask` `{question}` → answer with citations | brief is regenerated when its inputs hash changes; `ask` = SQL status + vector search over the account's interactions, tenant and account filters injected server-side |
| Catalog | `GET /providers`, `GET /opponents`, `GET /experiences`, `POST/PATCH` on each (role ops+) | writes re-index the item in `catalog_items` (via outbox → worker) |
| Catalog search | `POST /catalog/opponents:match` `{sport, gender, age_group, country, level_score, query?, limit?}`; `POST /catalog/experiences:search` | port of draft `findOpponents` / `findExperiences` |
| Contacts | `GET /contacts`, `GET /contacts/{id}`, `POST /contacts` | |
| Leads | `GET /leads?status=`, `GET /leads/{id}`, `POST /leads`, `PATCH /leads/{id}` | `POST` emits `lead.created` |
| Trips | `GET /trips?status=&from=`, `GET /trips/{id}` (with items), `POST /leads/{id}/trips:draft`, `PATCH /trips/{id}` (status), `GET /trips/{id}/quote` | draft = deterministic planner + pricing snapshot |
| Trip items | `PATCH /trip-items/{id}` (status, notes), `POST /trip-items/{id}:swap-opponent` `{opponent_id}` | emit `trip_item.status_changed` |
| Public proposal | `GET /public/proposals/{trip_id}?sig=` | unauthenticated, HMAC-signed link, read-only projection |
| Conversations | `POST /conversations`, `GET /conversations/{id}/messages` (text projection), `POST /conversations/{id}/messages` → `text/event-stream` | SSE events keep the draft `AgentEvent` shape: `text`, `tool_start`, `tool_end`, `done`, `error`. If the conversation is bound to a flow, the message is delivered as a signal and the stream relays that execution's `say` outputs |
| Flows | `GET /flows`, `POST /flows`, `GET /flows/{id}`, `PUT /flows/{id}/draft`, `POST /flows/{id}:validate`, `POST /flows/{id}:publish`, `GET /flows/{id}/versions`, `POST /flows/{id}:archive`, `GET /flow-node-types` (JSON Schema per node type, drives editor forms) | publish validates the graph, freezes a version, syncs `flow_triggers`, (re)creates Temporal schedules |
| Executions | `POST /flows/{id}:run` `{payload}` (manual trigger), `GET /executions?flow_id=&status=&subject=`, `GET /executions/{id}` (with node runs), `POST /executions/{id}:cancel`, `POST /executions/{id}:retry` `{from_node_id?}` | `retry` starts a new execution reusing prior outputs up to the node |
| Webhooks | `POST /hooks/{flow_key}` | per-trigger secret (HMAC header); responds 202 with execution id |
| Digest | `GET /digest/today?format=json\|html\|text` | morning brief: top risks (reason + next action + link), payments due/overdue, approvals waiting, departures in 14 days, leads unanswered > 1 business day. Facts deterministic; the 2–3 sentence opening is model-written and rejected if it contains a number not in the facts ([daily-digest.md](daily-digest.md)) |
| Approvals | `GET /approvals?status=pending`, `POST /approvals/{id}:decide` `{decision, comment}` | decision → Temporal signal `approval_decided` |
| Documents | `POST /documents` (multipart or signed-URL flow: `POST /documents:upload-url` then `POST /documents/{id}:ingest`), `GET /documents`, `GET /documents/{id}`, `DELETE /documents/{id}`, `GET /ingestion-jobs/{id}` | large files go straight to GCS via signed URL |
| Search | `POST /search` `{query, filters?, k?, rerank?}` → hits with citations | the RAG query endpoint (also an MCP tool) |
| Traces | `GET /agent-runs?surface=`, `GET /agent-runs/{id}` (steps + transcript), `GET /metrics/agents` (p50/p95, tool error rate, cost) | |
| Events | `GET /events?type=&subject=` | read-only view of the outbox for debugging |
| Admin | `GET /healthz` (liveness), `GET /readyz` (DB), `POST /admin/reindex` (owner) | |

**Implemented today:** `GET /me`, `GET /trips`, `GET /trips/{id}`, `GET /accounts`, `GET /accounts/{id}`, `/healthz`, `/readyz`; approvals, flows and executions answer 501. Being built in wave 2: `/accounts/{id}/brief`, `/accounts/{id}/ask`, approvals, flows, executions and the MCP server at `/mcp`.

OpenAPI is generated by FastAPI and published at `/openapi.json`; `apps/web` generates its TypeScript client from it (`openapi-typescript`), so web ↔ core contracts are typed end to end.

## 4. Event model

### 4.1 Outbox pattern

1. A repository write and its `outbox_events` row are committed **in the same transaction** (`EventWriter.add(event)` inside the unit of work). No event is ever published for a write that rolled back, and no write is ever left without its event.
2. A dispatcher claims undispatched rows with `SELECT … FOR UPDATE SKIP LOCKED LIMIT n` (safe with many core instances), and for each event:
   - matches enabled `flow_triggers` of kind `event` (type + JSON filter on payload) for the tenant;
   - starts one `FlowExecutionWorkflow` per match with **workflow id = `evt-{event_id}-{flow_version_id}`** — Temporal rejects duplicates, so redelivery is harmless (exactly-once start, at-least-once delivery);
   - performs internal reactions (e.g. re-index a catalog item);
   - sets `dispatched_at`; on failure increments `attempts`, stores `last_error`, backs off exponentially; after 10 attempts the event is parked and surfaced in the panel.
3. Dispatch latency target: < 2 s p95. The dispatcher wakes on Postgres `LISTEN/NOTIFY` (`NOTIFY outbox` in the same transaction) and falls back to a 5 s poll.

Why not Pub/Sub for this: the outbox already gives durable, transactional, ordered-per-subject delivery and Temporal gives idempotent starts; adding a broker in between adds a hop without adding a guarantee. If fan-out to external consumers is needed later, the dispatcher publishes to Pub/Sub as one more reaction.

### 4.2 Event catalog (v0)

| Event | Emitted when | Typical flows |
|---|---|---|
| `contact.created` | new contact | — |
| `lead.created` | lead stored (chat, webhook, manual, flow) | inbound-inquiry |
| `lead.status_changed` | status transition | follow-up on `proposal_sent` without reply |
| `trip.drafted` | `trips:draft` | proposal approval |
| `trip.status_changed` | e.g. → `confirmed` | pre-departure check |
| `trip_item.status_changed` | item requested/confirmed/cancelled | escalate cancellations |
| `approval.decided` | approval decided | (internal; also a signal) |
| `document.ingested` / `document.ingestion_failed` | ingestion workflow ends | notify ops |
| `message.received` | inbound message on a conversation not bound to a running execution | chat-triggered flows |

Event envelope (Pydantic, versioned): `{id, type, version, tenant_id, subject: {type, id}, occurred_at, actor: {type, id}, payload}`.

Time-based triggers (`trip.departure_in(30d)`) are not events: they are `wait` nodes (durable timers) inside a flow started by `trip.status_changed → confirmed`. Cron triggers are Temporal Schedules created on publish.

## 5. MCP tool catalog

Server: FastMCP (`mcp` Python SDK), Streamable HTTP at `/mcp`, stateless mode, auth by API key with scopes. Tools are thin adapters over `igs_common.agents.tools`, the **same definitions** the internal agents use, so behavior can't drift between "Claude Code operating IGS" and "our own agents". Every write records `audit_log` with `actor_type = api_key|agent`.

Approval column: **gated** = the tool does not perform the change; it creates an `approvals` row (or a flow execution with an approval node) and returns its id. Destructive or customer-facing actions are gated.

| Tool | Description (as shown to the model) | R/W | Approval | Annotations |
|---|---|---|---|---|
| `search_knowledge` | Search IGS policies, provider contracts, destination guides and past trip reports. Returns cited passages. | R | — | readOnly |
| `find_opponents` | Find opponent clubs matching sport, gender, age group, country and level (1-10). | R | — | readOnly |
| `find_experiences` | Find cultural/sport experiences in a country, optionally for a sport. | R | — | readOnly |
| `list_leads` | List leads filtered by status/date. | R | — | readOnly |
| `get_lead` | Lead with contact and conversation summary. | R | — | readOnly |
| `list_trips` | Trips filtered by status and departure window. | R | — | readOnly |
| `get_trip` | Trip with day-by-day items, providers and statuses. | R | — | readOnly |
| `list_unconfirmed_items` | Items still pending/requested, optionally for one trip or departure window. | R | — | readOnly |
| `trip_readiness` | Pre-departure readiness: per traveler, missing/overdue/invalid entry documents (passport validity, Brazil e-Visa, parental consent for minors, insurance) with due dates and sources. Also `GET /v1/trips/{id}/readiness`. | R | — | readOnly |
| `get_quote` | Price per person and breakdown for a trip. | R | — | readOnly |
| `list_executions` / `get_execution` | Flow executions and node-level results. | R | — | readOnly |
| `list_pending_approvals` | Approvals waiting for a decision. | R | — | readOnly |
| `daily_digest` | Morning digest facts (risks, payments, approvals, departures, stale leads) with links. | R | — | readOnly |
| `create_lead` | Create a qualified lead from coach details. | W | — | idempotent (by Idempotency-Key) |
| `update_traveler_document` | Record one requirement's collection status for a traveler (`missing → requested → received → verified`, or `not_applicable`). Status and dates only, audited. | W | — | idempotent |
| `draft_trip` | Build an itinerary + quote for a lead (status `proposed`). | W | — | |
| `update_trip_item` | Change an item's status/notes (`requested`, `confirmed`). | W | — | idempotent |
| `swap_opponent` | Replace the opponent of a match item. | W | gated if trip is `confirmed` | |
| `set_trip_status` | Move a trip through its lifecycle. | W | gated for `confirmed`, `cancelled` | destructive for `cancelled` |
| `cancel_trip_item` | Cancel a booked item. | W | gated | destructive |
| `send_proposal` | Send the proposal link to the coach. | W | gated (customer-facing) | openWorld |
| `request_provider_confirmations` | Start the confirmation flow for all pending items of a trip. | W (starts flow) | — | openWorld |
| `run_flow` | Manually trigger a published flow with a payload. | W | — | |
| `decide_approval` | Approve/reject a pending approval. Only for API keys with `approvals:decide` scope. | W | — | |

Scopes: `read`, `write`, `approvals:decide`, `flows:run`. A Claude Code key for an ops person typically has `read write flows:run`; deciding approvals stays human unless a key is explicitly given `approvals:decide`.

## 6. Agent runtime

Two entry points, one implementation (`igs_common.agents`):

| | Interactive (core) | Flow node (worker) |
|---|---|---|
| Trigger | `POST /conversations/{id}/messages` | `agent` node activity |
| Output | SSE stream to the client | final message + structured output into `vars` |
| Tools | per-surface allow-list (coach chat: read tools + `create_lead`, `draft_trip`) | tools selected in the node config, from the same registry |
| Limits | max 12 model iterations, request timeout 120 s | same iteration cap, activity timeout 5 min, Temporal retries on 429/5xx only |

Boundaries and rules:
- **Model**: OpenAI (Responses API) behind the provider-agnostic `igs_common.llm.LLMClient`; the model is chosen per role (`agent`, `chat`, `extractor`, `judge`, `simulator`, `fast`, `reasoning`) from `IGS_LLM_MODELS`, and per flow node by role reference. Prompt caching on system prompt + tool definitions (`prompt_cache_key`).
- **History is append-only**: full content blocks are persisted in `messages`; history is never edited or truncated in place (compaction, if needed, is done by the API's server-side compaction, not by rewriting rows).
- **Tool execution**: inputs validated with Pydantic before running; errors returned as `is_error` tool results; parallel tool calls executed concurrently and returned in one message; every call recorded in `agent_steps`.
- **Grounding**: prices, policies and availability come only from tools; the system prompt forbids inventing them and evals check it.
- **Prompt-injection posture**: tool outputs and retrieved documents are data. Customer-facing and destructive actions are approval-gated regardless of what the model decides.
- **No direct DB access from prompts**: the agent can only do what a tool exposes; tools enforce tenant scope and role.
- **Tracing**: one `agent_runs` row per turn (tokens, cost, latency, stop reason, OTel trace id), linked to the conversation or flow node run.

## 7. Tooling and local setup

| Tool | Use |
|---|---|
| uv (workspace) | dependency management, `uv run` entry points (`igs seed`, `igs worker`, `igs dispatcher`) |
| Python 3.13 | runtime (3.14 is installed locally but some native wheels — `temporalio`, `asyncpg`, ML deps — may lag; pin 3.13 in `.python-version`) |
| FastAPI + Uvicorn, Pydantic v2, pydantic-settings | API |
| SQLAlchemy 2 (async) + asyncpg, Alembic | data |
| temporalio | workflows/activities |
| openai, mcp | agents (via `igs_common.llm`), MCP server |
| opentelemetry-sdk + GCP exporter | traces |
| pytest, pytest-asyncio, testcontainers (Postgres+pgvector), Temporal test env (`WorkflowEnvironment.start_time_skipping`) | tests |
| ruff (lint+format), pyright (strict on `py-common`) | quality |

Local environment check (2026-10-22, this machine):

| Requirement | Status | Action |
|---|---|---|
| Python 3.13 | ✅ 3.13.11 (`python3.13`); default `python3` is 3.14.6 | pin 3.13 via `.python-version` |
| uv | ✅ 0.12.21 | — |
| Docker | ✅ running; `igs-os-db-1` (pgvector/pg17) on :5433 | add Temporal dev server to `docker-compose.yml` (`temporalio/temporal` image running `server start-dev`) so no local CLI install is needed |
| Temporal CLI | ❌ missing | optional: `brew install temporal` for `temporal workflow …` debugging |
| gcloud | ✅ 589.0.0 | needed from phase 6 (`gcloud auth application-default login` for Vertex in phase 2 if testing against real Vector Search) |
| Terraform, Helm | ❌ missing | phase 6: `brew install terraform helm` |
| kubectl | ⚠️ present but `--version` flag rejected (newer kubectl uses `kubectl version --client`) | verify in phase 6 |

## 8. Review of the stopped TypeScript drafts (PLAN.md §7)

| File | Verdict | Notes |
|---|---|---|
| `src/components/ui/button.tsx`, `card.tsx`, `cn.ts`, `index.ts` | **Keep** → `apps/web` | Clean, token-based (`bg-brand`, `bg-card`, `border-border`, `text-muted`) |
| `src/components/ui/badge.tsx` | **Keep, fix** | Uses `info/success/warning/danger` color tokens that no `globals.css` defines yet; add them to the theme. Status map covers lead/trip/item statuses; add `waiting/running/succeeded/failed` for executions and `approved/rejected/expired` for approvals |
| `src/app/proposal/[id]/print.css`, `print-button.tsx` | **Keep** | Proposal page will read `GET /v1/public/proposals/{id}` instead of the domain layer |
| `src/app/chat/sse.ts` | **Keep** | Correct incremental SSE parser; works unchanged against core's SSE |
| `src/app/chat/types.ts` | **Keep, then generate** | `AgentEvent` matches core's SSE contract (§3); later generated from the OpenAPI/JSON Schema instead of hand-mirrored |
| `src/app/api/chat/route.ts` | **Drop** | Imports the TS agent and Drizzle directly. Its two good ideas move to core: keep draining the agent after client disconnect (so a `tool_use` never lacks its `tool_result`), and text-only projection of history. Web calls core's SSE directly (CORS) or via a 10-line proxy if cookies require same-origin |
| `src/app/api/conversations/route.ts` | **Drop** | Replaced by `POST /v1/conversations` |
| `src/db/seed.ts` | **Port** → `igs seed` | Python version upserts instead of `TRUNCATE … CASCADE` (truncating `leads/trips` on every seed would wipe demo work) and routes knowledge through ingestion |
| `src/lib/search.ts` | **Port** → `igs_common.retrieval.search` | Keep the logic: hard filters, rank by `abs(level diff)` then similarity, "empty sports array = any sport". Vector part moves to `VectorStore` |
| `src/db/schema.ts` | **Port** → SQLAlchemy models | Per data-model.md; embeddings leave Postgres |
| `src/db/seed-data.ts` | **Port** → `packages/py-common/igs_common/fixtures/` | Content unchanged; knowledge entries become documents |
| `src/lib/embeddings.ts`, `src/db/index.ts`, `drizzle.config.ts` | **Drop** after port | Local transformers.js embeddings replaced by the `Embedder` implementations |
