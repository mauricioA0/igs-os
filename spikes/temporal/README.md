# Temporal spike — flow graph interpreter

Proves the flow-engine core on Temporal: a workflow that interprets a JSON graph
(`draft → approval → send`), with the approval node as a **signal + durable 48h timer**,
continue-as-new on long histories, and a **replay test** for determinism.

```bash
uv run pytest -q
```

Uses the time-skipping test environment (no server to run). Findings: `docs/architecture/temporal.md`.
