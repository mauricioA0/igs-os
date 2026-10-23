"""`VectorStore` protocol and the in-memory reference implementation.

Every store runs the same hybrid recipe so evals mean the same thing everywhere:
dense (cosine) + lexical (full text) [+ sparse dot product] → RRF. Reranking happens one level
up, in `igs_common.rag.retrieve`, so all stores share one reranker.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from typing import Protocol

from igs_common.rag import filters
from igs_common.rag.embed import tokenize
from igs_common.rag.fusion import rrf
from igs_common.rag.types import Chunk, Filter, Hit, SearchRequest, SearchResult


class VectorStore(Protocol):
    async def upsert(self, chunks: Sequence[Chunk]) -> None:
        """Insert or replace by `chunk_id`. Idempotent."""
        ...

    async def delete_where(self, tenant_id: str, filter: Filter) -> int:
        """Delete the tenant's chunks matching `filter`; returns how many were removed."""
        ...

    async def search(self, req: SearchRequest) -> SearchResult:
        """Hybrid search scoped to `req.tenant_id`. Quarantined chunks never come back."""
        ...


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def bm25_scores(
    query: str, docs: dict[str, str], *, k1: float = 1.2, b: float = 0.75
) -> dict[str, float]:
    terms = set(tokenize(query))
    if not terms or not docs:
        return {}
    tokenized = {cid: tokenize(text) for cid, text in docs.items()}
    avg_len = sum(len(t) for t in tokenized.values()) / len(tokenized) or 1.0
    df = Counter(term for toks in tokenized.values() for term in set(toks) & terms)
    n = len(tokenized)
    scores: dict[str, float] = {}
    for cid, toks in tokenized.items():
        tf = Counter(toks)
        score = 0.0
        for term in terms:
            if not tf[term]:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * tf[term] * (k1 + 1) / (tf[term] + k1 * (1 - b + b * len(toks) / avg_len))
        if score > 0:
            scores[cid] = score
    return scores


def ranked(scores: dict[str, float], limit: int) -> list[str]:
    return [cid for cid, _ in sorted(scores.items(), key=lambda kv: -kv[1])[:limit]]


def fuse(
    by_id: dict[str, Chunk],
    dense: list[str],
    lexical: list[str],
    sparse: list[str],
    top_k: int,
) -> list[Hit]:
    rankings = [r for r in (dense, lexical, sparse) if r]
    names = [n for n, r in (("dense", dense), ("lexical", lexical), ("sparse", sparse)) if r]
    positions = {
        n: {cid: i + 1 for i, cid in enumerate(r)} for n, r in zip(names, rankings, strict=True)
    }
    hits = []
    for rank, (cid, score) in enumerate(rrf(rankings)[:top_k], start=1):
        signals = {n: float(pos[cid]) for n, pos in positions.items() if cid in pos}
        hits.append(
            Hit(chunk=by_id[cid].without_vectors(), score=score, rank=rank, signals=signals)
        )
    return hits


class InMemoryStore:
    """Brute force, no network. Used by unit tests and dry-run evals."""

    def __init__(self) -> None:
        self._chunks: dict[str, Chunk] = {}
        self.quarantined: set[str] = set()

    def __len__(self) -> int:
        return len(self._chunks)

    async def upsert(self, chunks: Sequence[Chunk]) -> None:
        for chunk in chunks:
            self._chunks[chunk.chunk_id] = chunk

    async def delete_where(self, tenant_id: str, filter: Filter) -> int:
        doomed = [
            cid
            for cid, c in self._chunks.items()
            if c.tenant_id == tenant_id and filters.matches(c.payload(), filter)
        ]
        for cid in doomed:
            del self._chunks[cid]
        return len(doomed)

    async def search(self, req: SearchRequest) -> SearchResult:
        filters.normalize(req.filter)  # same validation as the real stores
        pool = {
            cid: c
            for cid, c in self._chunks.items()
            if c.tenant_id == req.tenant_id
            and cid not in self.quarantined
            and filters.matches(c.payload(), req.filter)
        }
        dense: list[str] = []
        if req.query_dense is not None:
            dense = ranked(
                {cid: cosine(req.query_dense, c.dense) for cid, c in pool.items() if c.dense},
                req.candidates,
            )
        lexical = ranked(
            bm25_scores(req.query, {cid: f"{c.title} {c.text}" for cid, c in pool.items()}),
            req.candidates,
        )
        sparse: list[str] = []
        if req.query_sparse is not None:
            sparse_scores = {
                cid: req.query_sparse.dot(c.sparse) for cid, c in pool.items() if c.sparse
            }
            sparse = ranked({k: v for k, v in sparse_scores.items() if v > 0}, req.candidates)
        return SearchResult(hits=fuse(pool, dense, lexical, sparse, req.top_k))
