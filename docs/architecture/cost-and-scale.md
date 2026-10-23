# Cost and scalability

Status: planning estimate, 2026-10-22.

**Assumptions:** GCP region `us-central1`, the stack described in [`docs/PLAN.md`](../PLAN.md). Infrastructure prices are left out of this public version; the model (LLM) cost per unit is kept because it is what grows with usage.

## 1. Fixed footprint

| Service | Demo | Prod (per replica × replicas) |
|---|---|---|
| frontend | 0.25 vCPU / 0.5 GB | 0.5 / 1 GB × 2 |
| history | 0.5 / 1 GB | 1 / 4 GB × 3 |
| matching | 0.25 / 0.5 GB | 0.5 / 1 GB × 2 |
| internal worker | 0.25 / 0.5 GB | 0.25 / 0.5 GB × 1 |
| web UI | 0.25 / 0.5 GB | 0.25 / 0.5 GB × 1 |
| **Total** | **1.5 vCPU / 3 GB** | **5.5 vCPU / 16 GB** |


## 2. Variable cost

LLM provider: **OpenAI**, one model per role (`IGS_LLM_MODELS`; ids verified against the Models API, prices from the official pricing page, 2026-10-22, in `packages/py-common/pricing/models.yaml`). Per MTok, short context (input / cached input / output): `gpt-6.1-sol` (roles agent, judge) **$2 / $0.10 / $10**; `gpt-6-luna` (roles chat, extractor, fast, simulator) **$0.10 / $0.01 / $0.50**; `gpt-6-astra` (role reasoning, used sparingly) **$10 / $1 / $50**. Reasoning tokens are billed as output and are included in the output estimates below.

> These figures were first priced on Claude-equivalent tiers and re-priced for OpenAI after the provider switch.

### 2.1 Per 1,000 coach conversations

Assumed conversation: 8 coach turns. The agent makes ~2 model calls per turn (tool use, then answer), so 16 calls.

| Token type | Per call | Per conversation |
|---|---|---|
| Cached prefix (system + tool definitions) | 3,000 | 48,000 cache reads |
| Uncached input (history + tool results, growing) | ≈ 4,000 average | 64,000 |
| Output (reasoning at low effort + text / tool calls) | ≈ 500 | 8,000 |

| Agent model | Cost per conversation | **Per 1,000 conversations** |
|---|---|---|
| `gpt-6-luna` (role `chat`, the configured coach-chat model) | 64k×$0.10 + 48k×$0.01 + 8k×$0.50 ≈ $0.011 | **≈ $11** |
| `gpt-6.1-sol` (role `agent`) | 64k×$2 + 48k×$0.10 + 8k×$10 ≈ $0.21 | **≈ $213** |
| `gpt-6-astra` (role `reasoning`) | 64k×$10 + 48k×$1 + 8k×$50 ≈ $1.09 | **≈ $1,090** |

Infrastructure per conversation is negligible next to the LLM:
- Cloud Run CPU ≈ 16 × 0.3 s.
- 8 query embeddings and 8 vector queries.
- ≈ 50 DB writes.


**Cost lever:** the model is chosen per role and per flow node (`{"role": …}`), and the choice is made with the eval suite, not by guess. The coach chat runs on the cheap tier; the agent tier is used where tool use quality matters.

### 2.2 Per 1,000 flow executions

Assumptions:
- A Temporal history event costs nothing on self-hosted Temporal beyond DB I/O.
- One 10-node execution ≈ 150–250 history events ≈ 300–500 persistence writes.

| Flow | LLM work per execution | LLM cost | Infra (worker CPU + DB) | **Per 1,000 executions** |
|---|---|---|---|---|
| Inbound inquiry (agent qualifies, extract, draft trip, approval, send) | Agent (`gpt-6.1-sol`): 4 calls × (5k in, 600 out). Extract (`gpt-6-luna`): 3k in / 300 out. Classify (`gpt-6-luna`): 1k / 50 | ≈ $0.064 + $0.0005 + $0.0001 ≈ $0.065 | ≈ 2 vCPU-s + ~400 writes ≈ $0.0001 | **≈ $65** |
| Pre-departure check (timers, provider requests, escalation) | Summary only (`gpt-6-luna`): 2k in / 200 out | ≈ $0.0003 | ≈ $0.0001 | **≈ $0.40** |
| Post-match report | Task agent (`gpt-6.1-sol`): 6k in / 800 out | ≈ $0.02 | ≈ $0.0001 | **≈ $20** |

**Takeaways:**
- Flows without LLM nodes are essentially free at the margin on self-hosted Temporal. Temporal Cloud would bill per action. At these volumes, self-hosting trades that bill for the fixed footprint in §1.
- The marginal cost lives entirely in the agent nodes. Node-level model and effort selection in the flow editor is a real cost control, not a cosmetic one.
### 2.3 RAG ingestion

- Embedding runs on the self-hosted models service (BGE-M3); 100k chunks take minutes of accelerator time, measured in §3.6.
- **OpenAI `text-embedding-3-large` baseline:** verify the current price on the OpenAI pricing page before the eval run.

## 3. Scalability

### 3.1 Request path

```
Vercel → Cloud Run core-api ─┬─ Cloud SQL (app)
                             ├─ GPU service (embed/rerank) ─ Vector Search
                             ├─ OpenAI API
                             └─ Temporal frontend (start / signal)
Temporal history/matching ── Cloud SQL (temporal) ── workers (GKE) ── OpenAI API / Cloud SQL / Vector Search
```

### 3.2 Bottlenecks, in the order they will bite

| # | Bottleneck | Limit | Symptom | Mitigation |
|---|---|---|---|---|
| 1 | **OpenAI API rate limits** (input/output tokens per minute and requests per minute, per org tier) | Org usage tier; at ≈ 9k uncached input tokens/min per active conversation, a few hundred concurrent conversations hit a low tier | 429s, latency spikes | Every model call goes through a Temporal activity with retry + backoff. Cap per-task-queue activity rate. Prompt caching (verify that cache reads are excluded from ITPM for current models). Raise the usage tier before launch. Route cheap nodes to Haiku |
| 2 | **Postgres connections** | Cloud SQL `max_connections` scales with memory (≈ 50 at 1.7 GB, a few hundred at 8–16 GB). Cloud Run can scale `core-api` to 100 instances × pool 10 = 1,000 connections | `too many connections`, cascading 5xx under burst | **Yes, a pooler is needed** before going public: PgBouncer (transaction mode) as a Deployment on the GKE cluster, or Cloud SQL managed connection pooling if available on the chosen edition (verify). Set Cloud Run `max-instances` and a per-instance pool of 5. Use the asyncpg-compatible transaction-mode settings (no server-side prepared statements) |
| 3 | **Temporal persistence (Cloud SQL Postgres)** | State transitions per second are bounded by DB write IOPS/latency, not by shards. 512 history shards is plenty for this scale. A single 4 vCPU instance realistically sustains hundreds to low thousands of transitions/s (measure, §3.6) | Rising schedule-to-start latency, history service CPU idle while DB is busy | Separate Temporal DB from app DB (prod mode). Scale the instance vertically, then use more SSD (IOPS scale with size). Keep payloads small: store large node outputs in GCS / app DB and pass references |
| 4 | **Workers** | Bounded by slots (`max_concurrent_activities`) × replicas | Task-queue backlog grows | Scale replicas on backlog (§3.4). Separate task queues for LLM-bound and CPU-bound activities |
| 5 | **GPU embedding / rerank** | Single L4: high throughput for short queries with batching; ingestion bursts saturate it | Retrieval p95 up, ingestion slow | Cloud Run GPU `max-instances` > 1. Dedicated ingestion service (batch) vs query service (low latency). Cache query embeddings |
| 6 | **Vector Search** | QPS per replica depends on machine type and index (expect hundreds to low thousands QPS per replica for < 1M vectors) | Retrieval p95 up | Autoscaling replicas. Filter by `tenant_id` in the index. Larger machine for p99 |
| 7 | **Cloud Run concurrency** (`core-api`) | Default 80 concurrent requests per instance. SSE chat streams hold a slot for the whole answer | Instance count balloons on long streams | Async FastAPI with concurrency 80–250 (I/O bound). Streams come from model calls, so instances mostly wait on network. Set `max-instances` consistent with the pooler |

**Top bottleneck in practice:**
- **Under real LLM traffic:** the OpenAI rate limit is the first wall.
- **Under synthetic load with mocked LLM:** Postgres connections (#2), then Temporal persistence writes (#3).

### 3.3 What to scale first

1. **Pooler + Cloud SQL sizing.** Cheap, and it removes the most likely outage.
2. **OpenAI usage tier + prompt caching + model routing per node.**
3. **Worker replicas on backlog.**
4. **Temporal DB vertical scaling / separation.**
5. **GPU `max-instances` + Vector Search replicas.**

### 3.4 Where Temporal workers run (recommendation for the plan)

> **Resolved:** PLAN v3 adopted the recommendation below — workers run on GKE Autopilot with KEDA (see `infra/k8s/`).

The first plan put workers on Cloud Run. Temporal workers are **long-polling pullers**: they receive no HTTP requests. So request-based Cloud Run never scales them, and they need always-allocated CPU.

Two workable options:
- **Recommended:** run workers on the **same GKE Autopilot cluster**, autoscaled on task-queue backlog with KEDA's Temporal scaler (verify the KEDA version that ships it) or an HPA on Temporal's `approximate_backlog_count` metric. Same cluster, same network to the Temporal frontend, no extra product.
- **Alternative:** **Cloud Run worker pools** (pull-based workloads), scaled manually or by a small controller on backlog.


### 3.5 Targets for "super scalable" (claims we will back with numbers)

| Path | Target |
|---|---|
| Retrieval API (embed + hybrid search + rerank, top-5) | **500 RPS sustained, p95 < 300 ms**, 0.1% errors |
| Chat API with mocked LLM (SSE, 2 s streamed answer) | **1,000 concurrent streams**, p95 time-to-first-byte < 500 ms |
| Flow starts (10-node flow, LLM activities mocked at 2 s) | **200 executions/s started, 2,000 in flight**, schedule-to-start p95 < 500 ms |
| Ingestion | **10,000 documents** (≈ 100k chunks) fully indexed in < 30 min |
| Elasticity | 0 → peak in 60 s with min-instances 0 (cold starts measured and reported) |

### 3.6 Load-test plan

**Tools:**
- **k6** for HTTP and SSE paths. Scripts in `loadtest/k6/`, run from a GCE VM in `us-central1` or k6 Cloud, never from a laptop.
- **Temporal [`omes`](https://github.com/temporalio/omes)** (Temporal's load generator) or a Python starter script for workflow throughput.
- **Mock OpenAI-compatible server** in `loadtest/mock_llm/`: a stub that streams fixed-size responses with configurable latency and injectable 429s. This tests *our* system, not Anthropic's. A separate small real-LLM run measures actual rate-limit behavior.

**Scenarios:**
1. **Baseline**: 10 RPS per path for 10 min, to record p50/p95/p99 and per-request cost.
2. **Ramp**: retrieval 0 → 1,000 RPS over 15 min; find the knee (first point where p95 doubles).
3. **Flow throughput**: start rate 50 → 400 executions/s. Watch:
   - schedule-to-start latency;
   - Cloud SQL CPU and IOPS;
   - history service CPU;
   - task-queue backlog.
4. **Approval storm**: 5,000 executions parked on `approval`, then 5,000 signals in 60 s.
5. **Spike**: 0 → 500 RPS in 60 s at min-instances 0, measuring cold starts (`core-api`, GPU).
6. **Soak**: 50% of target for 2 h, checking memory growth, connection leaks and Temporal shard balance.
7. **Chaos (prod mode)**: kill a history pod and fail over Cloud SQL HA during scenario 3. Executions must complete with no duplicate side effects (idempotency keys).

**Observability during tests:**
- Cloud Monitoring dashboards for Cloud Run, Cloud SQL, GKE and Vector Search.
- Temporal server Prometheus metrics, scraped by Managed Prometheus.
- OpenTelemetry traces in Cloud Trace.

**Output:** a results table committed to `docs/architecture/load-test-results.md` with:
- throughput at the knee;
- p95 per path;
- cost per 1,000 requests at that load;
- the limiting resource.

That table is what backs "super escalable" in the README.

## 4. Demo mode vs prod mode

One Terraform variable: `mode = "demo" | "prod"` in `infra/terraform/`.

| Setting | `demo` | `prod` |
|---|---|---|
| Temporal + worker pods | Spot, 1 replica each | Regular, replicas per §1.2, PodDisruptionBudgets |
| Cloud SQL | 1 shared zonal `db-g1-small` (app + temporal DBs) | 2 dedicated HA instances, PITR, larger SSD |
| Connection pooler | PgBouncer 1 replica (still required) | PgBouncer 2 replicas |
| Vector Search | 1 node, smallest machine (or usage-based tier) | Autoscaling, ≥ 2 replicas |
| Cloud Run `core-api` | min 0 | min 2 |
| GPU service | min 0, warm-up job before a demo | min 1 |
| Temporal Web UI | `kubectl port-forward` | HTTPS LB + IAP |
| Vercel | Hobby | Pro |
| Budget alert | Alerts at 50/90/100% | Per environment |

**Before a demo** (`make demo-warm`):
- hit `/healthz` on `core-api`;
- embed a dummy query to load the GPU model;
- start one smoke flow.

That removes cold starts from a first-time visitor's first click.

**Pause / resume** (`make pause`, `make resume`):
- scale GKE deployments to 0;
- set Cloud SQL `activation-policy=NEVER`;
- undeploy the Vector Search index (re-deploy takes minutes and keeps the data).


**Flip to prod** (`terraform apply -var mode=prod`):
1. Pre-create the dedicated Temporal Cloud SQL instance.
2. Migrate the `temporal` and `temporal_visibility` DBs with `pg_dump`/restore during a short maintenance window (stop workers, drain, restore, point Helm values to the new host, restart).
3. Raise the OpenAI usage tier.
4. Run the load-test suite (§3.6) against prod settings before announcing.

**History shards:** `numHistoryShards` is set to **512 in both modes** from day one. It cannot be changed after the cluster is created, which is why the flip above is a migration of the same cluster rather than a new one.
