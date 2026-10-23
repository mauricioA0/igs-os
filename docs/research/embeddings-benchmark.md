# Embeddings mini bake-off

**Status:** first pass, 2026-10-22. Code and raw results are in `spikes/embeddings/`.

**Decision:** adopted as the default in [`PLAN.md`](../PLAN.md) (Decisions → Embeddings): BGE-M3 hybrid, plus `bge-reranker-v2-m3` for agent answers, served by `services/models`. The re-run on the real ops corpus, with Qwen3-Embedding, `gemini-embedding-001` and OpenAI `text-embedding-3-large` as candidates, is still pending.

**TL;DR:** **BGE-M3 hybrid** (dense + 0.3 × sparse) is the best retriever here: MRR 0.976, with every relevant document in the top 3. It gets its dense and sparse vectors from a single forward pass. `bge-reranker-v2-m3` on top adds a little (MRR 0.981) for about 400 ms of CPU latency. Qwen3-Embedding-0.6B came last of the dense models on this corpus. The cheap `multilingual-e5-small` model tied BGE-M3 dense at ~15× less latency. **The corpus is tiny** (40 docs, 42 queries). Treat this as a sanity check that rules nothing in or out until we re-run on real operational documents.

## Results

CPU only (Apple M3 Max, float32, single query, median over 42 queries after one warm-up). Recall@1 for the two queries that have 2 relevant docs is capped at 0.5, so the maximum possible recall@1 is 0.976. One query is worth about 2.4 points.

| Configuration | Params | Dims | R@1 | R@3 | R@5 | MRR | MRR (EN, 32 q) | MRR (ES, 10 q) | Query p50 | Index 40 docs |
|---|---|---|---|---|---|---|---|---|---|---|
| multilingual-e5-small | 118M | 384 | 0.905 | 1.000 | 1.000 | 0.964 | 0.984 | 0.909 | 9 ms | 0.2 s |
| Qwen3-Embedding-0.6B, default instruction | 596M | 1024 | 0.833 | 0.952 | 1.000 | 0.910 | 0.904 | 0.927 | 103 ms | 1.9 s |
| Qwen3-Embedding-0.6B, domain instruction | 596M | 1024 | 0.762 | 0.976 | 0.976 | 0.877 | 0.871 | 0.894 | 125 ms | 1.9 s |
| BGE-M3 dense | 569M | 1024 | 0.905 | 1.000 | 1.000 | 0.964 | 0.984 | 0.909 | 137 ms | 1.9 s |
| BGE-M3 sparse only | 569M | — | 0.583 | 0.738 | 0.786 | 0.690 | 0.734 | 0.565 | 137 ms | 1.9 s |
| **BGE-M3 dense + 0.3·sparse** | 569M | 1024 | 0.929 | 1.000 | 1.000 | **0.976** | 0.968 | **1.000** | 137 ms | 1.9 s |
| ↳ + bge-reranker-v2-m3 (top-10) | +568M | — | **0.952** | 0.976 | 1.000 | **0.981** | 0.974 | 1.000 | 544 ms | — |

Not run:

- **OpenAI `text-embedding-3-large`**: `OPENAI_API_KEY` was not set in the environment. `bench.py` runs it automatically when the key is present.
- **Qwen3-Reranker-0.6B**: it needs its own chat-style prompt template (instruction + `<Query>`/`<Document>` + yes/no logits). A plain cross-encoder (query, doc) pair scored it at MRR 0.58, which reflects the missing template, not the model. It's left out until it is wired with that template.

## Method

- **Corpus**: the demo catalog in `src/db/seed-data.ts` (12 policy/FAQ chunks, 16 opponent clubs, 12 experiences), exported to `corpus.json` by `export-corpus.ts`. Each doc is one short paragraph (40-90 words). Structured fields (sport, gender, age groups, level) are rendered as text.
- **Golden set**: `golden.json`, 42 queries.
  - Language: 32 English, 10 Spanish.
  - Style: coach-style ("Two of our players are celiac") and ops-style ("rival femenino sub-15 tranquilo en Buenos Aires").
  - Many are paraphrased with no keyword overlap ("recovery day with thermal pools" → Arenal hot springs; "volunteer hours for school" → community clinic).
  - 40 queries have 1 relevant doc; 2 have 2.
- **Metrics**: recall@k = fraction of the relevant docs in the top k; MRR = 1/rank of the first relevant doc. Brute-force cosine over normalized vectors, so no ANN error is involved.
- **Model setup**:
  - e5 uses its `query:` / `passage:` prefixes.
  - Qwen3 uses its model-card `query` prompt (generic web search) or a domain instruction; documents have no prefix, as recommended.
  - BGE-M3 runs through `FlagEmbedding`; dense and lexical weights come from one `encode` call; hybrid = dense cosine + 0.3 × lexical matching score (the weighting from the BGE-M3 paper's ballpark, not tuned).
  - The reranker rescores the hybrid top-10.
- **Latency**: wall-clock to embed one query (plus reranking where listed), CPU, batch size 1. On a GPU (Cloud Run L4) all numbers drop sharply; the relative ordering of the CPU numbers is what matters here.

## Reading the results

- **Hybrid is the clearest win.** Sparse alone is weak (MRR 0.69), but adding it to dense fixes the cases where an exact term carries the meaning. Examples: "visa para Argentina con pasaporte americano", "cancel…30 días", "D1 college". Spanish MRR goes from 0.909 to 1.000. Vertex AI Vector Search supports dense + sparse hybrid queries, and BGE-M3 produces both vectors in one pass, so this maps directly onto the target architecture without a second model or a BM25 index.
- **The reranker fixes the remaining near-misses** ("Can parents come along?", "men's college team … barbecue"). It introduced one new miss ("Ballpark cost per player for Buenos Aires?" ranked the typical-itinerary doc above pricing). At about 400 ms on CPU, apply it selectively (agent-facing answers, not autocomplete), or run it on GPU.
- **Qwen3-0.6B underperformed here**, and the domain instruction made it *worse*. Plausible reasons:
  - The docs are very short.
  - Qwen3 is tuned for longer passages and instruction-following retrieval.
  - Its instruction is sensitive to wording, and we did not tune it.
  
  Its public MTEB lead (mostly on the 8B) is on very different data. That is not a verdict on the 4B/8B or on long contract PDFs.
- **multilingual-e5-small is a strong cheap baseline**: it ties BGE-M3 dense at 9 ms per query on CPU with 384-dim vectors (about 1/3 of the storage). Good candidate for low-stakes, high-volume paths or as a fallback.

## Threats to validity

- **Tiny, clean corpus.** 40 short docs make every model look good; R@5 is saturated at 1.0 for all dense models. Differences of 1-2 queries are within noise.
- **The same author wrote the corpus and the queries**, so vocabulary overlap is higher than with real user traffic, even with deliberate paraphrases.
- **Short paragraphs only.** No long documents, no chunking, no tables or PDFs: the real ops corpus (provider contracts, trip reports, emails) will behave differently.
- **One run, one machine**, CPU only, untuned hybrid weight and untuned Qwen3 instructions.

## Recommendation

1. **Default for Phase 2: BGE-M3, dense + sparse hybrid**, stored in Vertex AI Vector Search as dense + sparse vectors, with payload filters (`tenant_id`, `type`, `country`, `sport`…). Use **`bge-reranker-v2-m3`** on the top-10 for agent-facing retrieval. Both are MIT/Apache-licensed and can be served from one Cloud Run GPU service.
2. **Keep the embedding layer pluggable** and keep this harness. Before locking the choice, re-run it on the real ops corpus: chunked PDFs/contracts and 150-300 queries, ideally harvested from real ops and coach questions.
   - Candidates: BGE-M3 hybrid, Qwen3-Embedding-4B (GPU), Qwen3-Reranker with its proper template, `text-embedding-3-large` as the hosted baseline, and e5-small as the floor.
   - Also tune the hybrid weight and Qwen3 instructions on a train split; report on a held-out split.
3. **Put this benchmark in CI** (`uv run python bench.py`) so a model or chunking change shows its recall/MRR delta in the PR.

## Reproduce

```bash
cd spikes/embeddings
uv sync --python-preference only-managed --python 3.13   # native arm64 Python; the x86_64 one has no torch wheels
uv run python bench.py --device cpu                      # writes results.json
OPENAI_API_KEY=... uv run --with openai python bench.py  # optional hosted baseline
```

Models download to the default Hugging Face cache (`~/.cache/huggingface`), not into the repo.

## Re-run on the demo tenant golden sets (2026-10-22)

Corpus: the seeded demo tenant (54 Account 360 interactions + 12 knowledge documents), 60 golden
questions (40 Account 360 from `fixtures/account-qa.yaml`, 20 knowledge, EN/ES). BGE-M3 served
locally by `services/models` (CPU). Command:
`uv run python -m evals.run --suite embeddings --compare hash,models:bge-m3`.

| | recall@1 | recall@3 | recall@5 | recall@10 | hit@5 | MRR | nDCG@10 |
|---|---|---|---|---|---|---|---|
| hash-1024 (floor) | 0.200 | 0.463 | 0.619 | 0.772 | 0.700 | 0.450 | 0.515 |
| hash-1024 + BM25 | 0.317 | 0.547 | 0.713 | 0.829 | 0.783 | 0.537 | 0.605 |
| **BGE-M3 dense** | **0.450** | **0.768** | **0.824** | **0.961** | **0.900** | **0.725** | **0.763** |
| BGE-M3 + BM25 (RRF) | 0.376 | 0.628 | 0.775 | 0.940 | 0.850 | 0.612 | 0.686 |

Findings:
- BGE-M3 beats the lexical floor by +35% MRR and +11 points recall@5.
- **Naive RRF with BM25 hurts BGE-M3** (−0.11 MRR): BM25 is weak on Spanish questions over
  English sources and drags good dense ranks down. Next: weighted RRF and BGE-M3's own sparse
  vector instead of BM25, then the reranker on top; OpenAI `text-embedding-3-large` as a hosted
  reference once paid runs are approved.
