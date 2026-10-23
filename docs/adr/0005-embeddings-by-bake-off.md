# ADR 0005 — Embedding model chosen by bake-off

Status: Accepted · 2026-10-22

## Context
Coaches write in English, the ops team in Spanish, providers in Spanish/Portuguese. Leaderboards (MTEB) are general-purpose and partly self-reported. Candidate open models: Qwen3-Embedding (Apache 2.0, strong multilingual scores, matching reranker) and BGE-M3 (MIT, dense + sparse in one model). Personal OpenAI and Anthropic keys are available; Anthropic has no embedding model.

## Decision
Implement an `Embedder` interface with **Qwen3-Embedding-0.6B (+ Qwen3-Reranker)**, **BGE-M3 (+ bge-reranker-v2-m3)** and **OpenAI `text-embedding-3-large`** as hosted baseline. Pick the production model by recall@k / MRR / nDCG on a golden set built from IGS data. Exclude non-commercial or non-standard licenses (Jina, Gemma terms).

## Consequences
- The choice is defensible with numbers and repeatable when new models appear.
- Changing models later means re-embedding the corpus (ingestion supports a versioned `embed_model` field).
- Self-hosted models need GPU serving (see model-serving doc).
