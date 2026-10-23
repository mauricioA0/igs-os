# ADR 0002 — Temporal self-hosted on GKE Autopilot

Status: Accepted · 2026-10-22

## Context
Flows wait on humans (approvals), on conversations (next user message) and on dates ("30 days before departure"). Ingestion fans out over many documents. We need durable state, retries, timers and replay without holding resources. The owner wants a self-managed service inside GCP rather than a SaaS.

## Decision
Run the Temporal server ourselves on **GKE Autopilot** using the official Helm chart, with persistence and visibility on a dedicated **Cloud SQL Postgres** (no Elasticsearch). History shards fixed at 512. Web UI behind IAP. Workers run as separate services that scale on task-queue backlog. Local development uses `temporal server start-dev`.

## Consequences
- Durable timers and signals make approvals and long waits free; executions are replayable and debuggable.
- We own upgrades, schema migrations, capacity and the shard count (immutable after creation); a runbook and Terraform/Helm are required.
- GKE has a baseline cost even at idle.
- Workflow code must be deterministic; enforced through Temporal's sandbox and replay tests.
