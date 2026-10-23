"""Retrieval evals: embedders, retrievers and the golden-set runner.

Retrievers return fixture keys (interaction / document keys) so results compare directly with
the golden sets. Account-scoped questions are filtered to that account, like the API does.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal, Protocol
from uuid import UUID

from .costs import CostLedger
from .datasets import Doc, GoldenQuery
from .metrics import hit_at_k, ndcg_at_k, recall_at_k, reciprocal_rank, summarize

Kind = Literal["query", "passage"]
KS = (1, 3, 5, 10)


# ── Embedders ──────────────────────────────────────────────────────────────


class Embedder(Protocol):
    name: str

    async def embed(self, texts: Sequence[str], kind: Kind) -> list[list[float]]: ...


_TOKEN = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text.lower())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return _TOKEN.findall(folded)


class HashEmbedder:
    """Free, deterministic lexical baseline (signed feature hashing of words + bigrams).

    Not a semantic model: it's the floor every real embedder must beat, and what `--dry` uses.
    """

    def __init__(self, dims: int = 1024) -> None:
        self.dims = dims
        self.name = f"hash-{dims}"

    async def embed(self, texts: Sequence[str], kind: Kind) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        toks = tokens(text)
        feats = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:], strict=False)]
        vec = [0.0] * self.dims
        for f in feats:
            digest = hashlib.blake2b(f.encode(), digest_size=8).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dims
            vec[idx] += 1.0 if digest[4] & 1 else -1.0
        return _normalize(vec)


class OpenAIEmbedder:
    """Hosted baseline (paid). Cost goes to the ledger from the price table."""

    def __init__(self, model: str, ledger: CostLedger, batch: int = 64) -> None:
        from openai import AsyncOpenAI

        self.name = f"openai:{model}"
        self._model = model
        self._client = AsyncOpenAI()
        self._ledger = ledger
        self._batch = batch

    async def embed(self, texts: Sequence[str], kind: Kind) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self._batch):
            chunk = list(texts[i : i + self._batch])
            resp = await self._client.embeddings.create(model=self._model, input=chunk)
            self._ledger.add_tokens(f"embed:{self.name}", self._model, resp.usage.prompt_tokens)
            out.extend(_normalize(list(d.embedding)) for d in resp.data)
        return out


class ModelsServiceEmbedder:
    """Self-hosted BGE-M3 (dense) behind `services/models` `POST /embed`."""

    def __init__(self, base_url: str, model: str = "bge-m3", batch: int = 32) -> None:
        self.name = f"models:{model}"
        self._url = base_url.rstrip("/") + "/embed"
        self._model = model
        self._batch = batch

    async def embed(self, texts: Sequence[str], kind: Kind) -> list[list[float]]:
        import httpx

        out: list[list[float]] = []
        async with httpx.AsyncClient(timeout=120) as client:
            for i in range(0, len(texts), self._batch):
                payload = {"texts": list(texts[i : i + self._batch]), "kind": kind}
                resp = await client.post(self._url, json=payload)
                resp.raise_for_status()
                body: dict[str, Any] = resp.json()
                vectors = body.get("dense") or body.get("embeddings") or []
                out.extend(_normalize([float(x) for x in v]) for v in vectors)
        return out


def make_embedder(spec: str, ledger: CostLedger, models_url: str | None) -> Embedder:
    """`hash`, `openai:<model>` or `models:<name>` (needs `--models-url`)."""
    if spec == "hash" or spec.startswith("hash-"):
        dims = int(spec.split("-", 1)[1]) if "-" in spec else 1024
        return HashEmbedder(dims)
    if spec.startswith("openai:"):
        return OpenAIEmbedder(spec.split(":", 1)[1], ledger)
    if spec.startswith("models:"):
        if not models_url:
            raise ValueError(f"{spec} needs --models-url (services/models)")
        return ModelsServiceEmbedder(models_url, spec.split(":", 1)[1])
    raise ValueError(f"unknown embedder {spec!r}")


# ── Retrievers ─────────────────────────────────────────────────────────────


class Retriever(Protocol):
    name: str

    async def search(self, query: GoldenQuery, k: int) -> list[str]: ...


def _scope(corpus: Sequence[Doc], query: GoldenQuery) -> list[Doc]:
    """Account questions see only that account's interactions (server-side filter)."""
    if query.account is None:
        return list(corpus)
    return [d for d in corpus if d.account == query.account]


@dataclass
class MemoryRetriever:
    """Exact cosine (and optionally BM25 + RRF hybrid) over the fixture corpus, in memory."""

    embedder: Embedder
    corpus: Sequence[Doc]
    hybrid: bool = False
    name: str = ""
    _vectors: dict[str, list[float]] = field(default_factory=dict)
    _bm25: BM25 | None = None

    def __post_init__(self) -> None:
        self.name = self.name or (self.embedder.name + ("+bm25" if self.hybrid else ""))

    async def prepare(self) -> None:
        vectors = await self.embedder.embed([d.text for d in self.corpus], "passage")
        self._vectors = {d.id: v for d, v in zip(self.corpus, vectors, strict=True)}
        if self.hybrid:
            self._bm25 = BM25(self.corpus)

    async def search(self, query: GoldenQuery, k: int) -> list[str]:
        if not self._vectors:
            await self.prepare()
        scoped = _scope(self.corpus, query)
        (qv,) = await self.embedder.embed([query.question], "query")
        dense = sorted(scoped, key=lambda d: -_dot(qv, self._vectors[d.id]))
        ranked = [d.id for d in dense]
        if self._bm25 is not None:
            allowed = {d.id for d in scoped}
            lexical = [i for i in self._bm25.rank(query.question) if i in allowed]
            ranked = rrf([ranked, lexical])
        return ranked[:k]


class BM25:
    def __init__(self, corpus: Sequence[Doc], k1: float = 1.5, b: float = 0.75) -> None:
        self._docs = {d.id: Counter(tokens(d.text)) for d in corpus}
        self._len = {i: sum(c.values()) for i, c in self._docs.items()}
        self._avg = sum(self._len.values()) / max(len(self._len), 1)
        df: Counter[str] = Counter()
        for c in self._docs.values():
            df.update(c.keys())
        n = len(self._docs)
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self._k1, self._b = k1, b

    def rank(self, query: str) -> list[str]:
        q = tokens(query)
        scores: dict[str, float] = {}
        for doc_id, tf in self._docs.items():
            norm = self._k1 * (1 - self._b + self._b * self._len[doc_id] / self._avg)
            s = sum(
                self._idf.get(t, 0.0) * tf[t] * (self._k1 + 1) / (tf[t] + norm)
                for t in q
                if t in tf
            )
            if s > 0:
                scores[doc_id] = s
        return sorted(scores, key=lambda i: -scores[i])


def rrf(rankings: Sequence[Sequence[str]], k: int = 60) -> list[str]:
    """Reciprocal rank fusion, the same fusion the hybrid VectorStore uses."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda i: -scores[i])


class RagRetriever:
    """The production path: `igs_common.rag.retrieve` against a seeded + ingested database.

    Hits are mapped back to fixture keys through their metadata (`key`, `source_key`,
    `interaction_key` or `document_key`), which ingestion copies from the seed.
    """

    def __init__(self, tenant_id: UUID, account_ids: dict[str, UUID] | None = None) -> None:
        try:
            from igs_common import rag  # type: ignore[attr-defined]
        except ImportError as exc:  # pragma: no cover - depends on W1 landing
            raise RuntimeError("igs_common.rag is not available yet") from exc
        self._rag: Any = rag
        self._tenant = tenant_id
        self._accounts = account_ids or {}
        self.name = "igs_common.rag"

    async def search(self, query: GoldenQuery, k: int) -> list[str]:
        filters: dict[str, Any] = {}
        if query.account is not None and query.account in self._accounts:
            filters["account_id"] = str(self._accounts[query.account])
        hits = await self._rag.retrieve(query.question, self._tenant, filters, k)
        return [_hit_key(h) for h in hits]


def _hit_key(hit: Any) -> str:
    meta = getattr(hit, "metadata", None) or getattr(hit, "payload", None) or {}
    for attr in ("key", "source_key", "interaction_key", "document_key"):
        value = meta.get(attr) if isinstance(meta, dict) else None
        value = value or getattr(hit, attr, None)
        if value:
            return str(value)
    return str(getattr(hit, "id", ""))


# ── Runner ─────────────────────────────────────────────────────────────────


@dataclass
class RetrievalReport:
    retriever: str
    overall: dict[str, float]
    by_set: dict[str, dict[str, float]]
    by_lang: dict[str, dict[str, float]]
    misses: list[dict[str, Any]]
    per_query: list[dict[str, Any]]
    cost_usd: Decimal = Decimal(0)

    def as_dict(self) -> dict[str, Any]:
        return {
            "retriever": self.retriever,
            "overall": self.overall,
            "by_set": self.by_set,
            "by_lang": self.by_lang,
            "misses": self.misses,
            "per_query": self.per_query,
            "cost_usd": str(self.cost_usd),
        }


async def run_retrieval(
    retriever: Retriever, golden: Sequence[GoldenQuery], *, k_max: int = 10
) -> RetrievalReport:
    rows: list[dict[str, Any]] = []
    for q in golden:
        ranked = await retriever.search(q, k_max)
        metrics: dict[str, float] = {}
        for k in KS:
            metrics[f"recall@{k}"] = recall_at_k(ranked, q.sources, k)
        metrics["hit@5"] = hit_at_k(ranked, q.sources, 5)
        metrics["mrr"] = reciprocal_rank(ranked, q.sources)
        metrics["ndcg@10"] = ndcg_at_k(ranked, q.sources, 10)
        rows.append({"id": q.id, "set": q.set, "lang": q.lang, "ranked": ranked, **metrics})

    def group(key: str) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for value in sorted({r[key] for r in rows}):
            out[value] = summarize([_metrics(r) for r in rows if r[key] == value])
        return out

    misses = [
        {"id": r["id"], "expected": list(q.sources), "got": r["ranked"][:5]}
        for r, q in zip(rows, golden, strict=True)
        if r["hit@5"] == 0.0
    ]
    return RetrievalReport(
        retriever=retriever.name,
        overall=summarize([_metrics(r) for r in rows]),
        by_set=group("set"),
        by_lang=group("lang"),
        misses=misses,
        per_query=rows,
    )


def _metrics(row: dict[str, Any]) -> dict[str, float]:
    return {k: v for k, v in row.items() if isinstance(v, float)}


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))
