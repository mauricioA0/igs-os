# ADR 0006 — MCP as the single tool surface

Status: Accepted · 2026-10-22

## Context
Three kinds of callers need the same operations (list trips, confirm a provider, swap an opponent, search knowledge): our internal agents and flow `agent` nodes, the ops team's own AI assistants (Claude Code / Desktop), and the panel.

## Decision
Define operational tools once in `services/core` and expose them through an **MCP server** (Streamable HTTP, bearer/OAuth auth, read-only vs destructive annotations). Internal agents use the same tool definitions in-process. The panel calls the REST API, which shares the same domain functions.

## Consequences
- No drift between what a human's assistant and our agents can do; one place for validation, authorization and audit.
- Tool descriptions are part of the product and are covered by agent evals.
- MCP spec and auth evolve; we pin the SDK and test against it.
