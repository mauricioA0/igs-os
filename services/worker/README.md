# igs-worker

Temporal workers for IGS OS: `FlowExecution` (the flow interpreter) on the `flows` queue and
`IngestDocument` (RAG ingestion skeleton) on the `ingestion` queue.

```bash
uv run python -m igs_worker                 # both queues, Temporal at localhost:7233
uv run python -m igs_worker --queue flows   # one queue per process (one Deployment per queue in GKE)
uv run pytest services/worker/tests         # time-skipping test server, no Temporal needed
IGS_UPDATE_HISTORIES=1 uv run pytest services/worker/tests/test_replay.py  # re-record histories (on purpose only)
```

Settings (`IGS_WORKER_*`): `TEMPORAL_ADDRESS`, `TEMPORAL_NAMESPACE`, `TASK_QUEUE_FLOWS`,
`TASK_QUEUE_INGESTION`, `CODEC_KEY` (base64 AES-256, required when `ENVIRONMENT=production`),
`CODEC_KEY_ID`, `OTEL_ENABLED`, `MAX_NODE_RUNS_PER_RUN`, `INLINE_OUTPUT_MAX_BYTES`.

Layout: `workflows/flow_execution.py` (interpreter), `activities/` (node side effects, node-run
records, approvals, subflow version loading), `codec.py` (zlib + AES-GCM payload codec),
`expressions.py` (deterministic CEL + templates), `flow_model.py` (local adapter until the
generated flow models from `igs_common.flows` land).
