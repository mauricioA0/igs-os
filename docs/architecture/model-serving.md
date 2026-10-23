# Model serving — embeddings and reranker on GCP

Status: research for Phase 2 (RAG). Researched 2026-10-22 against primary docs (links at the end). Numbers marked **estimate** are not measured yet; Phase 2 replaces them with load-test results.

## 1. What we need to serve

| Model | Role | Size | Notes |
|---|---|---|---|
| `Qwen/Qwen3-Embedding-0.6B` | dense embeddings (candidate A) | ~0.6B | Last-token pooling, Matryoshka (can truncate dims). Queries need the instruction prefix `Instruct: <task>\nQuery: <q>`; documents don't. The prefix is client-side. |
| `Qwen/Qwen3-Reranker-0.6B` | cross-encoder reranker (pairs with A) | ~0.6B | Original checkpoint is a causal LM scored on "yes"/"no" tokens; needs `hf_overrides` in vLLM. |
| `BAAI/bge-m3` | dense + sparse (+ ColBERT) embeddings (candidate B) | ~568M | Sparse ("lexical weights") feeds the keyword side of hybrid search. Not Matryoshka. |
| `BAAI/bge-reranker-v2-m3` | cross-encoder reranker (pairs with B) | ~568M | XLM-RoBERTa sequence classification. |

Two traffic shapes:
- **Ingestion**: large, bursty batches of document chunks (throughput-bound, latency doesn't matter).
- **Query time**: one short query embedding + one rerank call over ~20–50 candidates per user question (latency-bound, low volume for IGS).

## 2. Cloud Run with GPU — facts that shape the design

| Fact | Value |
|---|---|
| GPU types | NVIDIA **L4** (24 GB, `nvidia-l4`), NVIDIA **RTX PRO 6000 Blackwell** (96 GB, `nvidia-rtx-pro-6000`). One GPU per instance. |
| L4 regions | `us-central1`, `us-east4`, `europe-west1`, `europe-west4`, `asia-southeast1`, `asia-south1` (invite only) |
| RTX PRO 6000 regions | `us-central1`, `europe-west4`, `asia-southeast1`, `asia-south2` |
| Minimum CPU / memory | L4: 4 vCPU / 16 GiB (8 vCPU / 32 GiB recommended). RTX PRO 6000: 20 vCPU / 80 GiB |
| Scale to zero | Yes. Instance with drivers ready in ~5 s; **model load time comes on top** of that. |
| Billing | Instance-based billing is **mandatory** with GPU. GPU billed for the whole instance lifetime. Min instances billed at full rate while idle. |
| Autoscaling signal | **Request concurrency, not GPU utilization.** `--concurrency` must be set deliberately. |
| Default quota | 3 GPUs per region per type (with zonal redundancy off) on first deploy. |
| Zonal redundancy | On by default (higher price). Off = best-effort failover, cheaper, quota easier to get. |
| Model loading | Bake into the image if < 10 GB (our models are ~1–2.5 GB each), or download from GCS at start (needs Direct VPC egress `all-traffic` + Private Google Access), or Cloud Storage FUSE mount. |
| Concurrency rule of thumb | `(model instances × parallel queries per model) + (model instances × ideal batch size)`, then load test. |


## 3. Serving engines

| Engine (version checked) | Qwen3-Embedding-0.6B | Qwen3-Reranker-0.6B | BGE-M3 dense | BGE-M3 sparse | bge-reranker-v2-m3 | Notes |
|---|---|---|---|---|---|---|
| **vLLM 0.32.0** (2026-10-18) | ✅ pooling runner, `/v1/embeddings` | ✅ with `hf_overrides` (below), `/rerank`, `/score` | ✅ `--hf-overrides '{"architectures":["BgeM3EmbeddingModel"]}'` | ✅ task `token_classify` via `/pooling` + `/tokenize` to map token ids | ✅ `XLMRobertaForSequenceClassification` | Covers all four. One pooling task per server process (`--pooler-config.task`); BGE-M3 dense+sparse in one call only via an IO-processor plugin that lives in vLLM's `tests/` tree — not a packaged feature. |
| **HF TEI 1.9.4** (2026-09-15) | ✅ Qwen3 listed | ❌ not listed (only XLM-RoBERTa/GTE/ModernBERT rerankers) | ✅ XLM-RoBERTa | ❌ sparse only for SPLADE models | ✅ XLM-RoBERTa seq. classification | Very fast startup, dynamic batching, small images. L4 = Ada → image `ghcr.io/huggingface/text-embeddings-inference:89-1.9`; CPU image `cpu-1.9`. |
| **Infinity 0.0.78** (2026-10-19, active) | ⚠️ Qwen2-style decoders "much slower" | ❌ rerankers must be BERT-style single-class | ✅ | ❌ "no sparse" | ✅ bge-reranker family | Multi-model in one process, dynamic batching, OpenAI-compatible. Pre-1.0. |

### Exact vLLM commands

```bash
# Qwen3 embedding
vllm serve Qwen/Qwen3-Embedding-0.6B --runner pooling

# Qwen3 reranker (original checkpoint)
vllm serve Qwen/Qwen3-Reranker-0.6B \
  --hf_overrides '{"architectures": ["Qwen3ForSequenceClassification"],"classifier_from_token": ["no", "yes"],"is_original_qwen3_reranker": true}'

# BGE-M3 dense (one process) …
vllm serve BAAI/bge-m3 --runner pooling \
  --hf-overrides '{"architectures": ["BgeM3EmbeddingModel"]}' --pooler-config.task embed
# … and BGE-M3 sparse (second process, same weights)
vllm serve BAAI/bge-m3 --runner pooling \
  --hf-overrides '{"architectures": ["BgeM3EmbeddingModel"]}' --pooler-config.task token_classify

# bge reranker
vllm serve BAAI/bge-reranker-v2-m3 --runner pooling
```

Pitfalls found in the docs:
- vLLM rejects a `dimensions` request on models not flagged Matryoshka (BGE-M3 errors explicitly). For Qwen3 confirm `is_matryoshka` in `config.json`; otherwise truncate + re-normalize client-side.
- Without the `BgeM3EmbeddingModel` override, BGE-M3 loads as plain XLM-RoBERTa and silently drops the sparse/ColBERT heads.
- `score` as a task name was removed in vLLM v0.21; use the classify/rerank path.
- Cloud Run mounts NVIDIA driver 580 (CUDA 13.0). Use a base image whose CUDA ≤ 13.0, or add forward-compat packages.

## 4. Recommended setup

### 4.1 Phase 2 (evaluation): one GPU service per candidate, scale to zero

The bake-off needs both model families running with identical infrastructure. vLLM is the only engine that serves all four models (including Qwen3-Reranker and BGE-M3 sparse), so one engine keeps the comparison fair.

```
models-qwen3   (Cloud Run, L4)  vLLM: Qwen3-Embedding-0.6B + Qwen3-Reranker-0.6B
models-bgem3   (Cloud Run, L4)  vLLM: bge-m3 (embed) + bge-m3 (token_classify) + bge-reranker-v2-m3
```

Several vLLM processes share one L4 (24 GB is plenty for ~0.6B models): give each `--gpu-memory-utilization 0.25`–`0.3` and front them with a tiny router (Caddy/nginx or a 30-line Starlette proxy) on port 8080, or run them on separate ports behind path-based routing in the same container.

Dockerfile sketch (`services/models/qwen3/Dockerfile`):

```dockerfile
# Pin: vLLM 0.32.0 published image; check its CUDA version is <= 13.0 (Cloud Run driver 580).
FROM vllm/vllm-openai:v0.32.0

ENV HF_HOME=/models HF_HUB_OFFLINE=1
# Bake weights into the image (< 10 GB) for predictable cold starts.
RUN HF_HUB_OFFLINE=0 huggingface-cli download Qwen/Qwen3-Embedding-0.6B \
 && HF_HUB_OFFLINE=0 huggingface-cli download Qwen/Qwen3-Reranker-0.6B

COPY start.sh router.py /app/
ENTRYPOINT ["/app/start.sh"]   # starts both vllm servers on :8001/:8002 + router on :8080
```

`start.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
vllm serve Qwen/Qwen3-Embedding-0.6B --runner pooling --port 8001 \
  --gpu-memory-utilization 0.3 --max-model-len 8192 &
vllm serve Qwen/Qwen3-Reranker-0.6B --port 8002 --gpu-memory-utilization 0.3 --max-model-len 8192 \
  --hf_overrides '{"architectures": ["Qwen3ForSequenceClassification"],"classifier_from_token": ["no", "yes"],"is_original_qwen3_reranker": true}' &
exec python /app/router.py   # /v1/embeddings -> 8001, /v1/rerank -> 8002, /health waits for both
```

Deploy (verify flag spelling with `gcloud run deploy --help`; the docs only show the zonal-redundancy flag as a placeholder):

```bash
gcloud run deploy models-qwen3 \
  --project mv-cloud-509914 --region us-central1 \
  --image us-central1-docker.pkg.dev/mv-cloud-509914/igs/models-qwen3:<tag> \
  --gpu 1 --gpu-type nvidia-l4 --no-gpu-zonal-redundancy \
  --cpu 8 --memory 32Gi --no-cpu-throttling \
  --min-instances 0 --max-instances 2 --concurrency 32 \
  --timeout 300 --no-allow-unauthenticated \
  --startup-probe httpGetPath=/health,initialDelaySeconds=0,periodSeconds=2,failureThreshold=150
```

- Private service (`--no-allow-unauthenticated`); callers (core API, workers) use their service account's ID token.
- `--concurrency 32` is a starting point from the rule of thumb (2 models × (8 parallel + 8 batch)); load test in Phase 2.
- Startup probe allows ~5 minutes for model load on first boot.

### 4.2 Production shape after the bake-off

| Path | Where | Why |
|---|---|---|
| Ingestion embeddings (batch) | GPU service, scale to zero, called by Temporal ingestion activities | Throughput; GPU only billed while batches run |
| Query embedding | **CPU-only Cloud Run**, min 1 instance — TEI `cpu-1.9` (Qwen3 or BGE-M3 dense) | One short query per question; keeps the hot path warm without paying for an always-on GPU |
| Query sparse vector (if BGE-M3 wins) | Same GPU service or CPU vLLM process; or replace with the vector store's built-in keyword/BM25 side | Only needed if Vector Search hybrid needs client-supplied sparse vectors |
| Rerank | GPU service, scale to zero, with `min-instances=1` scheduled during ops business hours (Cloud Scheduler toggling the setting) | Cross-encoder over 20–50 pairs is slow on CPU (**estimate**: hundreds of ms to seconds) |

Batching:
- **Ingestion**: Temporal activity sends 64–128 chunks per request, several requests in flight per worker; vLLM/TEI do continuous/dynamic batching on top. Activity retries handle cold starts (first call may take minutes).
- **Queries**: single request, no client batching; set a short client timeout with fallback to "dense only, no rerank" if the reranker is cold.

### 4.3 Alternatives considered

| Option | Verdict |
|---|---|
| **CPU-only Cloud Run for everything (0.6B models)** | Viable for query embeddings. Too slow for bulk ingestion and for reranking 50 pairs within an interactive budget (**estimate**, to measure). |
| **Vertex AI online prediction endpoint** with a vLLM container on L4 | Managed autoscaling and model registry, but historically needs ≥1 replica always on (no scale to zero by default) → ~always-on GPU cost. Revisit only if traffic is steady. |
| **Hosted embeddings** (OpenAI `text-embedding-3-large`, Vertex AI text embeddings, Vector Search auto-embeddings) | Zero ops, pay per token. Kept as the **baseline in the retrieval eval** (OpenAI) and as a fallback. |
| **RTX PRO 6000** | 96 GB is overkill for 0.6B models; ~2× L4 price and 20 vCPU / 80 GiB minimum. Only for the 4B/8B Qwen3 variants. |
| **Infinity** | Active and convenient (multi-model per process), but no Qwen3-Reranker or BGE-M3 sparse. |

## 5. Latency and cost expectations (to be replaced by measurements)

| Metric | Expectation | Status |
|---|---|---|
| Cold start, GPU service (driver ~5 s + container + model load from image) | ~30–90 s | **estimate** |
| Query embedding, warm, CPU TEI, short query | tens of ms | **estimate** |
| Query embedding, warm, L4 | < 20 ms | **estimate** |
| Rerank 30 pairs × ~300 tokens, warm, L4 | ~50–150 ms | **estimate** |
| Ingestion throughput, 0.6B on L4 | thousands of chunks/minute | **estimate** |
| Ingesting 100k chunks | well under one GPU-hour | **estimate** |
| Idle shape | CPU query service always on; GPU only when used | recommendation |

## 6. mv-cloud check (read-only, 2026-10-22)

- Project ID is **`mv-cloud-509914`** (display name "mv-cloud").
- Enabled already: `run`, `aiplatform`, `artifactregistry`, `compute`.
- Cloud Run regions available include `us-central1` (L4 + RTX PRO 6000) and `southamerica-east1` (no Cloud Run GPU there). GPU quota was not checked; request L4 quota in `us-central1` (no zonal redundancy) before Phase 2 deploys.

## Sources

- Cloud Run GPU configuration: https://docs.cloud.google.com/run/docs/configuring/services/gpu
- Cloud Run GPU best practices: https://docs.cloud.google.com/run/docs/configuring/services/gpu-best-practices
- Cloud Run pricing: https://cloud.google.com/run/pricing (figures above from the Cloud Billing Catalog API, service `152E-C115-5142`)
- vLLM pooling models: https://docs.vllm.ai/en/latest/models/pooling_models.html
- vLLM embedding models: https://docs.vllm.ai/en/latest/models/pooling_models/embed.html
- vLLM scoring / rerankers: https://docs.vllm.ai/en/latest/models/pooling_models/scoring.html
- vLLM model-specific (BGE-M3): https://docs.vllm.ai/en/latest/models/pooling_models/specific_models.html
- vLLM releases: https://pypi.org/project/vllm/
- HF Text Embeddings Inference, supported models and images: https://huggingface.co/docs/text-embeddings-inference/supported_models
- Infinity: https://github.com/michaelfeil/infinity
