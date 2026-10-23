# igs-models

Embeddings and reranking for IGS OS retrieval:

- **`POST /embed`** — BGE-M3, dense (1024-d, L2-normalized) **and** sparse (lexical weights) in one pass.
- **`POST /rerank`** — bge-reranker-v2-m3 cross-encoder, scores in [0, 1].
- **`GET /healthz`** — `{"status": "ok"}` once both models are loaded.

Own uv project (not a member of the root workspace) because torch is heavy and only this service needs it. Callers use `igs_common.rag`'s HTTP clients (the `Embedder`/`Reranker` protocols), never this package directly.

## API

```http
POST /embed
{"texts": ["Do US citizens need a visa for Brazil?"], "kind": "query"}
→ {"model": "BAAI/bge-m3", "dim": 1024, "dense": [[...]], "sparse": [{"30089": 0.30, ...}]}
```

`kind` is accepted for interface symmetry with other embedders; BGE-M3 uses no query/passage prefixes. Sparse keys are tokenizer ids (strings), max-pooled per id, special tokens dropped — the same format Vertex Vector Search sparse vectors and the pgvector `sparsevec` path consume after mapping.

```http
POST /rerank
{"query": "visa Brazil", "documents": ["tango", "US citizens need an e-visa"], "top_n": 1}
→ {"model": "BAAI/bge-reranker-v2-m3", "results": [{"index": 1, "score": 0.68}]}
```

Results are sorted by score (ties by input order); `index` points into `documents`.

Limits (env `IGS_MODELS_*`, see `src/igs_models/settings.py`): 128 texts per embed request, 100 documents per rerank, 8,000 chars per text → **413** above them. Tokens beyond 512 are truncated. Requests are split into micro-batches of 32 and run on one inference thread, so concurrent requests queue instead of oversubscribing the CPU.

## Supply chain

- Revisions pinned to full commit shas and upstream weight files pinned by sha256 (`src/igs_models/manifest.py`); a mismatch aborts the build.
- **Safetensors only at runtime.** Upstream BGE-M3 publishes pickled weights (`pytorch_model.bin`, `sparse_linear.pt`; no safetensors on any branch as of 2026-10-22). `scripts/prepare_models.py` converts them with `torch.load(weights_only=True)` (torch's restricted unpickler — tensors only, no code execution) at build time and writes a `manifest.json` with the sha256 of every shipped file.
- At startup each model directory is re-hashed against its manifest and refused if any `.bin`/`.pt` file is present.
- BGE-M3 is implemented on `transformers` (dense = CLS, sparse = ReLU(linear) max-pooled per token) instead of FlagEmbedding, so loading never touches pickles. Parity with FlagEmbedding's `BGEM3FlagModel`: max abs diff **0.0** on dense and sparse (golden in `tests/fixtures/bge_m3_golden.json`).

## Run locally

```bash
cd services/models
uv sync
uv run python scripts/prepare_models.py --out models   # ~4.5 GB; reuses ~/.cache/huggingface
uv run uvicorn igs_models.app:create_app --factory --port 8090
uv run pytest            # fast API tests with fake models
uv run pytest -m slow    # real weights: FlagEmbedding parity, cross-lingual, reranker, tamper check
```

## Docker (CPU)

```bash
docker build -t igs-models .          # from services/models; weights fetched in a build stage
docker run -p 8090:8080 igs-models
```

Linux builds pull the CPU-only torch wheel (`pytorch-cpu` index in `pyproject.toml`), no CUDA libraries. Image **5.7 GB** (≈4.4 GB of it is weights), runs as uid 10001, `HF_HUB_OFFLINE=1`. Resident memory with both models loaded: **3.4 GiB** — give Cloud Run ≥ 6 GiB.

## Measured latency (local, CPU)

Apple M3 Max, fp32, torch 2.14.1, over HTTP (uvicorn, one process), 2026-10-22. Passage ≈ 55 tokens.

| Call | p50 | max |
|---|---|---|
| `/embed` 1 query | **74 ms** | 78 ms |
| `/embed` batch of 32 passages | **686 ms** (≈21 ms/passage) | 718 ms |
| `/rerank` 10 documents | 316 ms | 329 ms |
| `/rerank` 32 documents | 858 ms | 876 ms |

Model load: ~3 s (BGE-M3) + ~2 s (reranker) from local disk. Expect a Cloud Run CPU instance (4–8 vCPU) to be 2–4× slower than this laptop; re-measure there before setting SLOs.

## GPU variant (vLLM) — per docs/architecture/model-serving.md

This CPU service is the default for the demo and for query-time embeddings. For bulk ingestion and low-latency rerank, the GPU shape from model-serving.md §4 is:

```bash
# one L4, three vLLM processes behind a small router on :8080
vllm serve BAAI/bge-m3 --runner pooling --port 8001 --gpu-memory-utilization 0.25 \
  --hf-overrides '{"architectures": ["BgeM3EmbeddingModel"]}' --pooler-config.task embed &
vllm serve BAAI/bge-m3 --runner pooling --port 8002 --gpu-memory-utilization 0.25 \
  --hf-overrides '{"architectures": ["BgeM3EmbeddingModel"]}' --pooler-config.task token_classify &
vllm serve BAAI/bge-reranker-v2-m3 --runner pooling --port 8003 --gpu-memory-utilization 0.25 &
```

- vLLM runs one pooling task per process, so dense and sparse BGE-M3 are two processes on the same weights. The router must keep **this service's request/response shapes** (`/embed` merges dense from :8001 with sparse from :8002 via `/tokenize` id mapping; `/rerank` maps vLLM's `/rerank` output) so `igs_common.rag` clients don't change.
- Deploy flags (verify spelling with `gcloud run deploy --help`): `--gpu 1 --gpu-type nvidia-l4 --no-gpu-zonal-redundancy --cpu 8 --memory 32Gi --no-cpu-throttling --min-instances 0 --max-instances 2 --concurrency 32 --no-allow-unauthenticated`, startup probe on `/healthz` with ~5 min budget.
- vLLM pulls weights from the Hub itself and reads BGE-M3's pickled `pytorch_model.bin`; to keep the safetensors-only rule, point it at the `/models/bge-m3` directory produced by `prepare_models.py` instead of the repo id.
- Cost: an L4 + 8 vCPU/32 GiB bills for every second it is up; scale to zero outside ingestion runs.
