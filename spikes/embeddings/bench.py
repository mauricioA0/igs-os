"""Mini bake-off: dense / sparse / hybrid retrieval + reranking on the IGS OS demo corpus.

Usage: uv run python bench.py [--device cpu|mps] [--out results.json]
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
CORPUS = json.loads((HERE / "corpus.json").read_text())
GOLDEN = json.loads((HERE / "golden.json").read_text())
DOC_IDS = [d["id"] for d in CORPUS]
DOC_TEXTS = [d["text"] for d in CORPUS]
KS = (1, 3, 5)

QWEN_TASK = (
    "Given a question from a sports tour coach or an operations staff member, "
    "retrieve the policy, opponent club or experience that answers it"
)


@dataclass
class Result:
    name: str
    params_m: float | None
    dims: int | None
    rankings: list[list[int]] = field(default_factory=list)  # doc indices per query, best first
    query_ms: list[float] = field(default_factory=list)
    index_s: float = 0.0
    notes: str = ""


def metrics(rankings: list[list[int]], subset: list[int] | None = None) -> dict[str, float]:
    idx = subset if subset is not None else range(len(GOLDEN))
    out = {f"recall@{k}": [] for k in KS} | {"mrr": []}
    for i in idx:
        rel = {DOC_IDS.index(r) for r in GOLDEN[i]["rel"]}
        ranked = rankings[i]
        for k in KS:
            out[f"recall@{k}"].append(len(rel & set(ranked[:k])) / len(rel))
        rr = next((1 / (pos + 1) for pos, d in enumerate(ranked) if d in rel), 0.0)
        out["mrr"].append(rr)
    return {k: float(np.mean(v)) for k, v in out.items()}


def rank_dense(encode_q: Callable[[str], np.ndarray], doc_emb: np.ndarray, r: Result) -> None:
    encode_q(GOLDEN[0]["q"])  # warm-up
    for g in GOLDEN:
        t = time.perf_counter()
        q = encode_q(g["q"])
        r.query_ms.append((time.perf_counter() - t) * 1000)
        scores = doc_emb @ q
        r.rankings.append(list(np.argsort(-scores)))


def count_params(model) -> float:
    return sum(p.numel() for p in model.parameters()) / 1e6


def run_sentence_transformer(
    name: str, model_id: str, device: str, q_kwargs: dict, d_kwargs: dict, notes: str = ""
) -> Result:
    import torch
    from sentence_transformers import SentenceTransformer

    # Some checkpoints (Qwen3) default to bfloat16, which is slow and lossy on CPU.
    model = SentenceTransformer(model_id, device=device, model_kwargs={"dtype": torch.float32})
    r = Result(name, count_params(model), model.get_sentence_embedding_dimension(), notes=notes)
    t = time.perf_counter()
    doc_emb = model.encode(DOC_TEXTS, normalize_embeddings=True, batch_size=16, **d_kwargs)
    r.index_s = time.perf_counter() - t
    rank_dense(lambda q: model.encode(q, normalize_embeddings=True, **q_kwargs), doc_emb, r)
    return r


def run_bge_m3(device: str) -> list[Result]:
    """Dense, sparse (lexical weights) and dense+sparse hybrid from a single BGE-M3 forward pass."""
    from FlagEmbedding import BGEM3FlagModel

    model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=False, devices=[device])
    params = count_params(model.model)

    t = time.perf_counter()
    docs = model.encode(DOC_TEXTS, return_dense=True, return_sparse=True, batch_size=16)
    index_s = time.perf_counter() - t
    d_dense = np.asarray(docs["dense_vecs"])
    d_sparse = docs["lexical_weights"]

    dense = Result("BGE-M3 (dense)", params, d_dense.shape[1])
    sparse = Result("BGE-M3 (sparse)", params, None, notes="learned lexical weights")
    hybrid = Result(
        "BGE-M3 (dense + 0.3·sparse)",
        params,
        d_dense.shape[1],
        notes="one forward pass yields both",
    )
    for r in (dense, sparse, hybrid):
        r.index_s = index_s

    model.encode([GOLDEN[0]["q"]], return_dense=True, return_sparse=True)  # warm-up
    for g in GOLDEN:
        t = time.perf_counter()
        q = model.encode([g["q"]], return_dense=True, return_sparse=True)
        ms = (time.perf_counter() - t) * 1000
        qd = np.asarray(q["dense_vecs"][0])
        qs = q["lexical_weights"][0]
        s_dense = d_dense @ qd
        s_sparse = np.array([model.compute_lexical_matching_score(qs, ds) for ds in d_sparse])
        for r, s in ((dense, s_dense), (sparse, s_sparse), (hybrid, s_dense + 0.3 * s_sparse)):
            r.query_ms.append(ms)
            r.rankings.append(list(np.argsort(-s)))
    return [dense, sparse, hybrid]


def run_openai() -> Result | None:
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    from openai import OpenAI  # type: ignore[import-not-found]

    client = OpenAI()
    model = "text-embedding-3-large"

    def emb(texts: list[str]) -> np.ndarray:
        data = client.embeddings.create(model=model, input=texts).data
        return np.asarray([d.embedding for d in data])

    r = Result(
        "OpenAI text-embedding-3-large", None, 3072, notes="hosted API; latency includes network"
    )
    t = time.perf_counter()
    doc_emb = emb(DOC_TEXTS)
    r.index_s = time.perf_counter() - t
    rank_dense(lambda q: emb([q])[0], doc_emb, r)
    return r


def rerank(base: Result, reranker_id: str, device: str, top_n: int = 10) -> Result:
    import torch
    from sentence_transformers import CrossEncoder

    ce = CrossEncoder(reranker_id, device=device, model_kwargs={"dtype": torch.float32})
    r = Result(
        f"{base.name} → {reranker_id.split('/')[-1]}", None, base.dims, notes=f"rerank top-{top_n}"
    )
    r.params_m = count_params(ce.model)
    ce.predict([(GOLDEN[0]["q"], DOC_TEXTS[0])])  # warm-up
    for i, g in enumerate(GOLDEN):
        cands = base.rankings[i][:top_n]
        t = time.perf_counter()
        scores = ce.predict([(g["q"], DOC_TEXTS[d]) for d in cands])
        r.query_ms.append(base.query_ms[i] + (time.perf_counter() - t) * 1000)
        reranked = [cands[j] for j in np.argsort(-np.asarray(scores))]
        r.rankings.append(reranked + base.rankings[i][top_n:])
    return r


def summarize(r: Result) -> dict:
    en = [i for i, g in enumerate(GOLDEN) if g["lang"] == "en"]
    es = [i for i, g in enumerate(GOLDEN) if g["lang"] == "es"]
    misses = [
        GOLDEN[i]["q"]
        for i in range(len(GOLDEN))
        if not set(r.rankings[i][:1]) & {DOC_IDS.index(x) for x in GOLDEN[i]["rel"]}
    ]
    return {
        "name": r.name,
        "params_m": round(r.params_m, 0) if r.params_m else None,
        "dims": r.dims,
        **{k: round(v, 3) for k, v in metrics(r.rankings).items()},
        "mrr_en": round(metrics(r.rankings, en)["mrr"], 3),
        "mrr_es": round(metrics(r.rankings, es)["mrr"], 3),
        "query_ms_p50": round(statistics.median(r.query_ms), 1),
        "index_s": round(r.index_s, 2),
        "notes": r.notes,
        "top1_misses": misses,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--out", default=str(HERE / "results.json"))
    args = ap.parse_args()
    dev = args.device

    results: list[Result] = []
    results.append(
        run_sentence_transformer(
            "multilingual-e5-small",
            "intfloat/multilingual-e5-small",
            dev,
            q_kwargs={"prompt": "query: "},
            d_kwargs={"prompt": "passage: "},
            notes="cheap baseline",
        )
    )
    results.append(
        run_sentence_transformer(
            "Qwen3-Embedding-0.6B (default instruction)",
            "Qwen/Qwen3-Embedding-0.6B",
            dev,
            q_kwargs={"prompt_name": "query"},
            d_kwargs={},
            notes="model card's generic web-search instruction",
        )
    )
    results.append(
        run_sentence_transformer(
            "Qwen3-Embedding-0.6B (task instruction)",
            "Qwen/Qwen3-Embedding-0.6B",
            dev,
            q_kwargs={"prompt": f"Instruct: {QWEN_TASK}\nQuery:"},
            d_kwargs={},
            notes="instruction written for this domain",
        )
    )
    results.extend(run_bge_m3(dev))
    if (oa := run_openai()) is not None:
        results.append(oa)

    best = max(results, key=lambda r: metrics(r.rankings)["mrr"])
    # Qwen3-Reranker needs its own chat-style prompt template; a plain (query, doc) pair scores
    # it unfairly, so it is left out until it is wired with that template.
    for reranker in ("BAAI/bge-reranker-v2-m3",):
        try:
            results.append(rerank(best, reranker, dev))
        except Exception as e:  # keep the bake-off running if one reranker fails to load
            print(f"reranker {reranker} failed: {e}")

    summary = {
        "device": dev,
        "n_docs": len(CORPUS),
        "n_queries": len(GOLDEN),
        "results": [summarize(r) for r in results],
    }
    Path(args.out).write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    cols = [
        "name",
        "params_m",
        "dims",
        "recall@1",
        "recall@3",
        "recall@5",
        "mrr",
        "mrr_en",
        "mrr_es",
        "query_ms_p50",
        "index_s",
    ]
    print(" | ".join(cols))
    for s in summary["results"]:
        print(" | ".join(str(s[c]) for c in cols))


if __name__ == "__main__":
    main()
