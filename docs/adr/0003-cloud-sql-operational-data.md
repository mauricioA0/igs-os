# ADR 0003 — Cloud SQL Postgres for operational data

Status: Accepted · 2026-10-22

## Context
Leads, trips, itinerary items, providers, flow definitions, executions and traces are relational and transactional. The vector store (ADR 0004) is not a system of record.

## Decision
Use **Cloud SQL for PostgreSQL** as the source of truth for operational data, with SQLAlchemy 2 (async) and Alembic migrations. Every table carries `tenant_id`. Temporal uses a separate Cloud SQL instance.

## Consequences
- Familiar, transactional, strong tooling; easy local parity with Docker Postgres.
- Vectors and their payloads must be kept in sync with Postgres rows (ingestion is idempotent by content hash and keyed by row/document IDs).
- Vertical scaling plus read replicas cover the expected load; AlloyDB is the upgrade path if needed.
