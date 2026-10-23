# Load tests

Prove the "scales horizontally" claim with numbers, without paid model calls. Method and targets:
[docs/architecture/cost-and-scale.md](../docs/architecture/cost-and-scale.md) §3 (bottlenecks,
load-test plan).

| Piece | What it is |
|---|---|
| `mock_llm/server.py` | OpenAI-compatible mock (Responses API, plain + streaming, Models API). Fixed latency (`MOCK_LATENCY_MS`, default 400) and chunk gap (`MOCK_TOKEN_DELAY_MS`, default 15), so API overhead is measured apart from model time |
| `k6/api_reads.js` | Ops panel read path as the public demo tenant: trips, accounts, Account 360 detail, pending approvals, execution detail |
| `k6/copilot_sse.js` | Copilot turns over SSE (`POST /v1/copilot/turns`) read to the `done` event, against the mock model |
| `k6/approvals_race.js` | N approvers decide the same pending approval at once: exactly one may win, the rest must get 409 |
| `run.sh` | Fresh isolated database (migrate + seed + demo reset), mock LLM, API, then k6 in Docker. Authenticated suites mint an ops API key automatically |

```bash
docker compose up -d db
loadtest/run.sh reads                        # VUS=20 RAMP=10s HOLD=20s by default
VUS=10 DURATION=30s loadtest/run.sh copilot
VUS=25 loadtest/run.sh approvals
```

Results go to `loadtest/results/<timestamp>-<suite>/` (`summary.json`, `k6.log`, `api.log`,
`mock.log`; gitignored). The public demo tenant is rate limited per client
(`igs_core.ratelimit`): only the read suite runs unauthenticated.

## Results

Template — copy a row per run; keep environment and git SHA so runs are comparable.

| Date | SHA | Env | Suite | VUs | Throughput | p50 | p95 | Errors | Notes |
|---|---|---|---|---|---|---|---|---|---|

### 2026-10-22 — local smoke (M3 Max laptop, 1 uvicorn worker, Postgres in Docker)

| Suite | VUs / duration | Throughput | p50 | p95 | Errors | Notes |
|---|---|---|---|---|---|---|
| reads | 20 / 25 s | 430 req/s | 31 ms | 84 ms | 0 / 10,750 | Account 360 detail p95 141 ms (computes rule-based health per request); trips p95 37 ms |
| copilot | 10 / 20 s | 10.8 turns/s | 887 ms | 1.2 s | 0 / 221 | Mock model ≈ 760 ms per turn → API overhead ≈ 130 ms median; TTFB p95 77 ms |
| approvals race | 25 at once | — | 116 ms | 131 ms | 0 | 1 winner, 24 × 409 — first-writer-wins holds under contention |

What it says and what it doesn't: a single API process on a laptop already clears the reads
target (p95 < 300 ms) with headroom; the copilot is bounded by the model, not the API. It says
nothing yet about Cloud SQL connection limits, Temporal persistence QPS or Cloud Run cold
starts — those need the same scripts against the deployed stack (cost-and-scale.md §3) with
PgBouncer in front of Cloud SQL and several API instances.

Found by these runs: a turn crashed when the provider omitted `cache_write_tokens` from usage
(cost math on `None`); fixed in `igs_common/llm/openai_client.py`.
