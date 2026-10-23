# PLAN.md red-team review (R1)

Scope: `docs/PLAN.md` against the goal. A solo builder answers "send me the best thing you've built" for an AI-native engineer role at Infinity Global Sports. The focus is ops run by agents and flows (Voiceflow/n8n-style), scalable, with Python RAG, self-hosted Temporal on GKE Autopilot, Vertex Vector Search and an embeddings bake-off.

Severity: **S1** blocks the goal · **S2** materially weakens the outcome · **S3** inconsistency or polish.

---

## S1 — Blockers

### 1. The first-time visitor's two-minute path is never defined or protected
§1 lists five things to see "within two minutes", but no phase produces a guided path, and the first click only becomes possible in Phase 6, the last build phase. Evaluators click one link. If it opens a login wall, an empty dashboard or a cold-started GPU, the evaluation is over.
**Edit PLAN.md**
- Add a **§1.1 Demo script**: landing → "Run the inbound-inquiry flow" button → watch the execution live (node by node) → approve it as ops → open the generated proposal → open the trace. One page links to the evals report and the repo.
- Auth (§8): decide now on **no login for a read-mostly public demo tenant** (data resets nightly) plus a protected "admin" for destructive actions. A login wall kills the two-minute path.
- Add an exit criterion to every phase from 3 on: *"the demo script works up to this step"*.

### 2. Sequencing ships the first visible thing last
Phases 1-4 are backend-only, and nothing is deployed until Phase 6. That leaves three risks: (a) cloud-only surprises (Vertex Vector Search API stage, GPU quota, GKE/Temporal networking) land at the end; (b) there is nothing to show if time runs out; (c) Vercel → Cloud Run → Temporal auth and CORS gets wired at the end.
**Edit PLAN.md**
- **Walking skeleton first**: in Phase 1, deploy `services/core` (hello + DB) to Cloud Run and `apps/web` (one page calling it) to Vercel. CI deploys on merge from day one.
- Move the "Verify Vector Search stage/limits" spike (§8) **into Phase 1**. It decides whether Phase 2 is even possible as planned.
- Reorder: **Flow engine (4) before Agent+MCP (3)**, or merge them. The `agent` node *is* the agent runtime, and the flow engine plus execution viewer are the differentiator. Build a vertical slice: one flow (inbound inquiry) end to end, including UI, before widening the node library.

### 3. Temporal self-hosted on GKE Autopilot is the largest ops cost, and it buys nothing visible
For a solo builder, running Temporal (frontend, history, matching and worker services, plus a Cloud SQL schema, shard count, upgrades, mTLS between workers on Cloud Run and a GKE-internal frontend, plus IAP for the UI) is weeks of infrastructure. It sits on the critical path of every flow. Cloud Run workers also need private connectivity to the GKE frontend (internal LB + Serverless VPC Access / Direct VPC egress), and that path is missing from the plan. Temporal workers on Cloud Run are a poor fit as well: they long-poll, so they need `min-instances ≥ 1`, CPU always allocated, and no request-based autoscaling. "Scale on the task queue" needs a custom metric. Cloud Run cannot do it out of the box.
**Edit PLAN.md**
- Keep Temporal (it is the right engine), but **run the workers on GKE Autopilot next to the server**, scaled by HPA/KEDA on Temporal's task-queue backlog metric. Drop "workers on Cloud Run".
- Add the network design: private GKE cluster, internal LB for the frontend, Cloud Run `core-api` → Direct VPC egress, mTLS or at minimum namespace-scoped API keys.
- Add a **fallback** if Phase 6 slips: the same code runs against Temporal Cloud by swapping the endpoint and certs. Note it as a pre-approved escape hatch, not a new decision.
- Consider whether `core-api` should also live on GKE, giving one runtime instead of Cloud Run + GKE + Cloud Run GPU. Fewer moving parts, the same scaling story.

### 4. The embeddings bake-off plus self-hosted GPU serving is over-engineered for the corpus size
The corpus is a few dozen fictional documents. Self-hosting two models (Qwen3-0.6B + reranker, BGE-M3 dense+sparse) on Cloud Run GPU means vLLM/TEI images, GPU quota requests (L4 in `us-central1` usually needs a quota increase), cold starts of 20–60 s and idle cost if min-instances is 1. A bake-off on ~50 golden questions over ~300 chunks also produces statistically meaningless differences.
**Edit PLAN.md**
- Run the **bake-off offline** (a notebook or `evals/retrieval` script, run on a laptop or one Colab GPU). Publish the table and the methodology. Serve **only the winner** in production.
- Make the dataset big enough to mean something: synthesize about 300–500 Q/A pairs from the corpus (LLM-generated, human-spot-checked) and report confidence intervals or bootstrap. Otherwise drop the "measured" claim.
- Production serving: prefer the **cheapest option that matches the winner**. If the winner is OpenAI or Vertex built-in embeddings, use the API with no GPU. If it is an open model, serve it on Cloud Run **CPU** (0.6B models run fine on CPU for query-time single embeddings) and run batch ingestion on a GPU job. Note: the `GPU` node in the diagram becomes optional.

### 5. Vertex AI Vector Search 2.0 / "Agent Retrieval" is an unverified dependency carrying the RAG story
Launch stage, Python SDK, sparse/hybrid semantics and pricing are all listed as "verify" (§8), but the architecture, ingestion and evals all assume them. If it is preview-only, REST-only or lacks BYO sparse vectors, both BGE-M3's sparse advantage and "hybrid + payload filters" break.
**Edit PLAN.md**
- Spike it in Phase 1 (see #2). Define a `VectorStore` port with two adapters: **pgvector on the same Cloud SQL** (the default and the test adapter) and Vertex Vector Search. Evals run against both.
- State the honest scaling story in the README: *"pgvector to ~10M vectors per tenant; adapter swaps to Vertex Vector Search for billion-scale; both tested in CI."* That is more convincing than a single managed dependency, and cheaper at idle.

---

## S2 — Material weaknesses

### 6. The "AI-native builder" evidence is under-specified
The job post asks how you build, not only what you built. §7 Delivery has a README section, but nothing in Phases 1–6 captures the evidence along the way.
**Edit PLAN.md**: add a cross-cutting **"Build log"** deliverable. Keep it in `docs/build-log.md`, plus the agent prompts and contracts used per phase (`docs/agents/`), eval-score history per commit (a chart in the README), the `CLAUDE.md` / skills used, and failures and what fixed them. Phase exit criteria include "build-log updated".

### 7. Two Postgres instances and a schema split are unplanned
§2 has "Operational data: Cloud SQL Postgres" and Temporal "dedicated Cloud SQL Postgres", but there is no instance, network or backup plan. Idle cost doubles: each Cloud SQL instance with HA is about $50–100+/month minimum.
**Edit PLAN.md**: one Cloud SQL instance with **separate databases** (`igs`, `temporal`, `temporal_visibility`) and separate users. Note it as a cost decision that can be reversed when load justifies it.

### 8. The flow engine has no data model or determinism rules
§4 is a feature list. What is missing:
- **Temporal determinism**: interpreting a graph inside a workflow is fine, but the published flow version must be passed in or loaded via an activity at start and never re-read mid-execution. Expressions must be pure. No `now()` or random values in workflow code.
- **History size**: long conversational flows (`capture` loops) and `loop/map` over many items will hit event-history limits (50K events / 50MB). Plan `continue-as-new` per N turns, and child workflows for `map` and `subflow`.
- **Retry from a node**: in Temporal this means a new execution seeded with the prior node outputs (reset to an event ID is fragile). Spec it.
- **Tables**: `flows`, `flow_versions`, `flow_executions`, `flow_node_runs`, `flow_triggers`, and how domain events are emitted (outbox table → trigger dispatcher) so `lead.created` actually starts flows.
**Edit PLAN.md**: add §4.1 "Engine invariants" with the items above, and the outbox pattern for domain-event triggers.

### 9. The node library is too wide for v0
There are about 20 node types across 6 categories, plus a schema-driven form editor. Most of them will be half-built.
**Edit PLAN.md**: define a **v0 node set** that exactly covers the 3 demo flows: `trigger`, `agent`, `extract`, `condition`, `domain_action`, `approval`, `wait`, `send_message`, `capture`/`say` (for the chat entry). Everything else goes to a "later" list. The editor can start with **read-only canvas + JSON** (already listed as a risk, so make it the plan).

### 10. Evals in CI need cost and secrets planning
Simulated multi-turn agent evals on every PR cost real money. Retrieval evals need the embedding service. The CI also needs Temporal (dev server) and Postgres.
**Edit PLAN.md**:
- PRs run deterministic tests + retrieval evals (cached embeddings) + a **small smoke subset** of agent/flow evals.
- Full suite nightly or on label, with a budget cap per run.
- Record cost per run in the eval report, which is itself a good AI-native signal.

### 11. The MCP server has no auth or tenancy design
It is exposed publicly from Cloud Run, and "same tools used by internal agents" means write tools such as `update_trip_item` and `approve`.
**Edit PLAN.md**: the MCP server uses bearer tokens scoped per tenant and role (read-only demo token published in the README; write token private), tool annotations (read-only/destructive), and every tool call recorded in the trace tables. Mention OAuth for MCP as "later".

### 12. Domain coverage is thin for "the operating system" of a tours company
The plan is strong on leads → proposal and provider confirmation. It misses the parts an ops lead at IGS would look for first: **rooming lists, payments/deposits schedule, traveler roster and documents (passports, waivers, medical), daily run-of-show for the tour leader, and incident handling**. One or two of these as data plus a flow would make the demo feel like *their* business.
**Edit PLAN.md**: add a "Domain v0" section. Use trips, items, providers and leads (existing), plus `travelers` (roster + documents status) and `payments` (deposit/balance due). Make demo flow 2 also chase missing traveler documents and the balance due at 45 days, both of which come from the policy text already in the seed.

---

## S3 — Inconsistencies and polish

13. **§2 Frontend "no direct DB access" vs §7** keeps `src/app/api/chat/route.ts` "as thin proxy or drop". Decide: **drop**. The browser calls `core-api` directly (CORS) or goes through a Vercel rewrite. One fewer hop to trace.
14. **The repo layout lacks a migration step**: the current repo is a single Next.js app in `src/`. Phase 1 should state "move to `apps/web`, update Vercel root directory and pnpm workspace". `docs/CONTRACTS.md` is TS-era and should be marked superseded.
15. **`packages/flow-schema`: "JSON Schema → Pydantic + TypeScript"**: pick a direction. Recommended: Pydantic is the source of truth, exported JSON Schema is committed, and TS types are generated with `json-schema-to-typescript` in CI with a diff check.
16. **Region**: Vector Search regions don't include `southamerica-east1`, and GPUs are scarce there. Decide on **`us-central1`** now and remove the open decision. Latency from Buenos Aires is fine for a demo.
17. **Model choices** are missing from §2: which Claude model per surface (agent vs `extract`/`classify` nodes vs eval judge/simulator), and the effort levels. State them, plus the rule "cheaper model for high-volume nodes, measured in evals".
18. **Observability duplication**: OpenTelemetry → Cloud Trace *and* own tables. Clarify that own tables are the product-facing source (runs, steps, node runs), and OTel is for infra debugging with a trace ID stored on each run to cross-link.
19. **Data reset / seeding for the public demo**: a nightly reset job (Temporal schedule, which also showcases the engine) that re-seeds the demo tenant and replays a few historical executions so the dashboards aren't empty.
20. **Licensing note**: Qwen3 is Apache-2.0 and BGE-M3 is MIT. Add a `THIRD_PARTY.md`. Voiceflow/n8n are used only as concept references, so cite them as inspiration.
21. **"Scales horizontally" needs proof**: add a small load test (k6 or Locust) in Phase 6 hitting retrieval plus starting about 1,000 flow executions, with numbers in the README. The claim without numbers is weaker than modest numbers.

---

## What a first-time visitor will actually click (priority for polish)

1. The landing page with the demo script button (most important).
2. A live flow execution, with nodes lighting up, the approval step, and the agent's tool calls.
3. The generated proposal.
4. The README: architecture diagram, eval charts, "how I built this with AI".
5. Maybe: MCP instructions, the traces page, the flow editor canvas.

Rarely clicked: the GKE/Temporal UI, Terraform, the embedding bake-off internals. Keep those as links and tables, and don't polish their UIs.

## Suggested revised phase order

| # | Phase | Exit |
|---|---|---|
| 1 | Python core + **walking skeleton deployed** (Cloud Run + Vercel + Cloud SQL) + Vector Search spike + build log | Public URL shows live data from core-api |
| 2 | Flow engine v0 on local Temporal + **inbound-inquiry vertical slice** (agent node, approval, execution viewer read-only) | Demo script steps 1–4 work locally |
| 3 | RAG: pgvector adapter, ingestion workflow, offline embeddings bake-off, retrieval evals | Bake-off table published; winner wired |
| 4 | Agent tools + MCP (scoped tokens) + agent/flow evals (smoke in PR, full nightly) | Thresholds green |
| 5 | Temporal on GKE Autopilot (+ workers on GKE, KEDA), Vertex Vector Search adapter, remaining demo flows, domain v0 additions | Full demo script on the public URL |
| 6 | Web polish (editor canvas, traces, proposal), load test, nightly demo reset | Numbers in README |
| 7 | Delivery: README, video, message | Sent |
