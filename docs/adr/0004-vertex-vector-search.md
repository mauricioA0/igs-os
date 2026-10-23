# ADR 0004 — Vertex AI Vector Search for vectors

Status: Accepted · 2026-10-22

## Context
RAG over operational documents must scale well beyond a demo and support hybrid retrieval with metadata filters per tenant. pgvector in the operational database was the simplest option; the owner chose a dedicated managed vector service.

## Decision
Store embeddings in **Vertex AI Vector Search** (Vector Search 2.0, now branded "Agent Retrieval": collections of JSON data objects, payload filters, hybrid search). Access goes through a `VectorStore` adapter with a local implementation for tests and CI.

## Consequences
- Scales independently of Postgres to very large corpora; managed indexing.
- The product was recently renamed and evolved; API churn is isolated behind the adapter. Launch stage, hybrid/sparse support and pricing must be verified in mv-cloud before Phase 2.
- A second store to keep consistent with Postgres; a baseline cost even with little data.
