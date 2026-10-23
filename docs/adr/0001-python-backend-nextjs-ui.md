# ADR 0001 — Python backend, Next.js UI only

Status: Accepted · 2026-10-22

## Context
IGS OS needs RAG, agents, a durable flow engine and model serving. The strongest ecosystem for those (Temporal Python SDK, the OpenAI and Anthropic SDKs, MCP SDK, embedding/reranking libraries, eval tooling) is Python. We also want a fast, polished UI with a public link.

## Decision
All business logic, AI and data access live in Python services (`services/core` on FastAPI, `services/worker` for Temporal). `apps/web` (Next.js on Vercel) is UI only and talks to `services/core` over HTTP; it never connects to the database.

## Consequences
- One place for domain rules, auth and tenancy; the UI can be replaced without touching logic.
- Shared types cross the language boundary via JSON Schema / OpenAPI (generated TS types), which must be kept in CI.
- Two runtimes to build and deploy; an extra network hop for UI reads.
