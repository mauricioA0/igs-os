# ADR 0007 — Own flow engine, inspired by Voiceflow and n8n

Status: Accepted · 2026-10-22

## Context
Ops needs both conversational flows (Voiceflow-style: say, capture, choices) and automations (n8n-style: triggers, nodes, branching, waits, approvals), with agents as first-class nodes and durable execution. Embedding n8n is not possible for a commercial product (Sustainable Use License); Voiceflow is a hosted SaaS.

## Decision
Build our own engine: versioned JSON flow graphs (draft → published), a node library, and one Temporal workflow per execution that interprets the graph (ADR 0002). We reuse **concepts** from Voiceflow and n8n, never their code, assets or proprietary formats.

## Consequences
- Full control over agent nodes, approvals, tenancy and observability; executions are durable and inspectable per node.
- Significant scope (schema, interpreter, editor, viewer); the editor may start as JSON + read-only canvas.
- Clean licensing for a public portfolio repo.
