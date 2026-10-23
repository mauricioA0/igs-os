# IGS OS — Documentation

New here? Read the [overview](OVERVIEW.md) (two pages), then the [plan](PLAN.md). Decisions and their reasons are recorded as [ADRs](#architecture-decision-records).

## Plan

| Doc | What it covers |
|---|---|
| [OVERVIEW.md](OVERVIEW.md) | Two-page technical overview: problem, what IGS OS does, architecture, key decisions, how quality is ensured, what's next |
| [PLAN.md](PLAN.md) | Plan v3: value for IGS, decisions, architecture, Account 360, flow engine, security, LLM roles and cost, phases with status, review disposition, open questions |
| [CONTRACTS.md](CONTRACTS.md) | How the parallel agent waves were organized: one owner per path, shared data shapes, ground rules (phase 1 and waves 2–4) |

## Architecture

| Doc | What it covers |
|---|---|
| [architecture/core-api.md](architecture/core-api.md) | `services/core` (FastAPI): REST surface, auth, events/outbox, MCP tool catalog, agent runtime |
| [architecture/data-model.md](architecture/data-model.md) | Postgres schema: catalog, sales, trips, Account 360, flows, executions, approvals, documents, audit; RLS and migrations |
| [architecture/temporal.md](architecture/temporal.md) | Self-hosted Temporal on GKE Autopilot + Cloud SQL: topology, shards, limits, determinism rules for the interpreter |
| [architecture/flow-engine.md](architecture/flow-engine.md) | Flow graph schema, triggers, node library, CEL expressions, interpreter workflow, approvals, publish checks |
| [architecture/rag.md](architecture/rag.md) | Ingestion, chunking, hybrid retrieval + rerank, pgvector and Vertex Vector Search adapters, citations |
| [architecture/model-serving.md](architecture/model-serving.md) | Serving BGE-M3 and the reranker: CPU Cloud Run today, vLLM on GPU for prod |
| [architecture/security.md](architecture/security.md) | Threat model and controls: tenant isolation, tool classes, approvals, MCP auth, prompt injection, minors' data, supply chain |
| [architecture/cost-and-scale.md](architecture/cost-and-scale.md) | LLM cost per unit (OpenAI prices), fixed footprint, scaling limits per component, load-test plan |
| [architecture/evals-and-testing.md](architecture/evals-and-testing.md) | Test pyramid, retrieval evals, agent evals with simulated users and a judge, flow evals, CI gates |
| [architecture/observability.md](architecture/observability.md) | OpenTelemetry end to end, GenAI spans, product trace tables, SLOs, alerts, cost per run |
| [architecture/frontend.md](architecture/frontend.md) | UI patterns: containers/presentational, controlled + uncontrolled components, HOCs, Zustand scoped per feature |

## Design (UX/UI)

| Doc | What it covers |
|---|---|
| [design/brand-reference.md](design/brand-reference.md) | Visual identity taken from infinityglobalsports.com: type, colors, country accents |
| [design/tokens.md](design/tokens.md) | Generated OKLCH design tokens, contrast checks, type scale, per-surface language |
| [design/ux-foundations.md](design/ux-foundations.md) | Personas, jobs-to-be-done, information architecture, object lifecycles, key journeys, UX principles |
| [design/ops-panel.md](design/ops-panel.md) | Ops app screen by screen: Today, trips, trip timeline, leads, providers, approvals, knowledge |
| [design/account-360.md](design/account-360.md) | Account 360: status, stakeholders, timeline, risks and a cited brief over client interactions |
| [design/flow-editor.md](design/flow-editor.md) | Flow editor and execution viewer UX, CEL editor, publish checks, test runs |
| [design/copilot.md](design/copilot.md) | Ops copilot: side panel + ⌘J, tool transparency, citations, approval cards, autonomy levels |
| [design/coach-experience.md](design/coach-experience.md) | Coach-facing chat, proposal brochure, trip portal |
| [design/demo-script.md](design/demo-script.md) | The 2-minute guided demo, tour overlay, demo tenant and reset strategy |
| [design/content-and-accessibility.md](design/content-and-accessibility.md) | Voice and tone, microcopy, formats, i18n, WCAG 2.2 AA checklist |

## Reviews

| Doc | What it covers |
|---|---|
| [reviews/plan-review.md](reviews/plan-review.md) | Red-team review of the plan: 21 findings with dispositions |
| [reviews/ux/README.md](reviews/ux/README.md) | Five UX reviews consolidated into ranked proposals |
| [reviews/ux/v1-ops-heuristics.md](reviews/ux/v1-ops-heuristics.md) | Nielsen heuristics + WCAG 2.2 AA on the ops panel |
| [reviews/ux/v2-flows.md](reviews/ux/v2-flows.md) | Flow editor and execution viewer vs. n8n, Voiceflow, Zapier, Temporal UI |
| [reviews/ux/v3-coach.md](reviews/ux/v3-coach.md) | Coach chat and proposal: brand, trust, conversion, mobile |
| [reviews/ux/v5-visual-system.md](reviews/ux/v5-visual-system.md) | Visual consistency, tokens, dark mode, benchmark vs. best-in-class |
| [reviews/security-2026-10.md](reviews/security-2026-10.md) | Security review of the code: findings with severity, fixes and what's open |

## Research

| Doc | What it covers |
|---|---|
| [research/embeddings-benchmark.md](research/embeddings-benchmark.md) | Embedding bake-off and the re-run on the demo tenant's golden sets (BGE-M3 vs. lexical floor, fusion finding) |

## Infrastructure

| Doc | What it covers |
|---|---|
| [infra/deployment.md](infra/deployment.md) | What runs where (GCP `mv-cloud-509914` + Vercel), cost per mode, pause/resume, how a deploy runs |
| [infra/runbook.md](infra/runbook.md) | Bootstrap order, deploy, rollback per component, codec-key rotation, demo reset, cost alerts, incidents |
| [../infra/terraform/README.md](../infra/terraform/README.md) | Terraform layout and what each environment creates |
| [../infra/k8s/README.md](../infra/k8s/README.md) | Temporal Helm values, workers, KEDA, IAP, NetworkPolicies |
| [../loadtest/README.md](../loadtest/README.md) | k6 load tests with a mock LLM and the recorded results |

## Delivery

| Doc | What it covers |
|---|---|
| [delivery/video-script.md](delivery/video-script.md) | Two-minute video script and shot list aligned to the guided tour |

## Architecture Decision Records

| ADR | Decision |
|---|---|
| [0001](adr/0001-python-backend-nextjs-ui.md) | Python backend, Next.js UI only |
| [0002](adr/0002-temporal-self-hosted-gke-autopilot.md) | Temporal self-hosted on GKE Autopilot |
| [0003](adr/0003-cloud-sql-operational-data.md) | Cloud SQL Postgres for operational data |
| [0004](adr/0004-vertex-vector-search.md) | Vertex AI Vector Search for vectors (pgvector first, behind the same adapter) |
| [0005](adr/0005-embeddings-by-bake-off.md) | Embedding model chosen by bake-off |
| [0006](adr/0006-mcp-single-tool-surface.md) | MCP as the single tool surface |
| [0007](adr/0007-own-flow-engine.md) | Own flow engine, inspired by Voiceflow and n8n concepts |
| [0008](adr/0008-nothing-from-employer.md) | Nothing from the author's employer |
