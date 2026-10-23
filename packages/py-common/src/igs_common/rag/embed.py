"""Embedders and rerankers: protocols, HTTP clients for `services/models`, deterministic fakes.

Models service contract (owned by `services/models`):

    POST /embed   {"texts": [...], "kind": "query" | "passage"}
               →  {"model": str, "dim": int, "dense": [[float]], "sparse": [{token_id: weight}]}
    POST /rerank  {"query": str, "documents": [str], "top_n": int | null}
               →  {"model": str, "results": [{"index": int, "score": float}]}  # best first
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Protocol

import httpx

from igs_common.rag.types import SparseVector

Embedding = tuple[list[float], SparseVector | None]

DEFAULT_DIMS = 1024  # BGE-M3 dense size; `document_chunks.embedding` is vector(1024)
DOCUMENT_BATCH = 64

_TOKEN = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text)]


class Embedder(Protocol):
    name: str
    dims: int
    sparse: bool

    async def embed_documents(self, texts: Sequence[str]) -> list[Embedding]: ...

    async def embed_query(self, text: str) -> Embedding: ...


class Reranker(Protocol):
    name: str

    async def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        """One relevance score per document, in input order (higher is better)."""
        ...


AuthHeader = Callable[[], Awaitable[str | None]]


class _ModelsClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
        auth_header: AuthHeader | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._auth = auth_header  # Cloud Run: returns "Bearer <ID token>"

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        headers = {}
        if self._auth is not None and (value := await self._auth()):
            headers["Authorization"] = value
        resp = await self._client.post(f"{self._base}{path}", json=body, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def aclose(self) -> None:
        await self._client.aclose()


class HttpEmbedder(_ModelsClient):
    """BGE-M3 (dense + sparse) served by `services/models`."""

    def __init__(
        self,
        base_url: str,
        *,
        name: str = "bge-m3",
        dims: int = DEFAULT_DIMS,
        sparse: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(base_url, **kwargs)
        self.name = name
        self.dims = dims
        self.sparse = sparse

    async def embed_documents(self, texts: Sequence[str]) -> list[Embedding]:
        out: list[Embedding] = []
        for start in range(0, len(texts), DOCUMENT_BATCH):
            out.extend(await self._embed(texts[start : start + DOCUMENT_BATCH], "passage"))
        return out

    async def embed_query(self, text: str) -> Embedding:
        return (await self._embed([text], "query"))[0]

    async def _embed(self, texts: Sequence[str], kind: str) -> list[Embedding]:
        if not texts:
            return []
        data = await self._post("/embed", {"texts": list(texts), "kind": kind})
        dense = data["dense"]
        sparse = (data.get("sparse") if self.sparse else None) or [None] * len(dense)
        if len(dense) != len(texts) or len(sparse) != len(texts):
            raise ValueError("models service returned a different number of embeddings")
        for vec in dense:
            if len(vec) != self.dims:
                raise ValueError(f"expected {self.dims}-dim vectors, got {len(vec)}")
        return [
            (list(map(float, d)), SparseVector.from_dict(s))
            for d, s in zip(dense, sparse, strict=True)
        ]


class HttpReranker(_ModelsClient):
    """bge-reranker-v2-m3 served by `services/models`."""

    def __init__(self, base_url: str, *, name: str = "bge-reranker-v2-m3", **kwargs: Any) -> None:
        super().__init__(base_url, **kwargs)
        self.name = name

    async def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        if not documents:
            return []
        data = await self._post("/rerank", {"query": query, "documents": list(documents)})
        scores = [float("-inf")] * len(documents)
        for item in data["results"]:
            scores[int(item["index"])] = float(item["score"])
        if any(s == float("-inf") for s in scores):
            raise ValueError("models service did not score every document")
        return scores


class HashEmbedder:
    """Deterministic, dependency-free embedder for tests and dry-run evals.

    Dense: hashed bag of words (L2-normalized), so texts sharing words are close.
    Sparse: hashed term frequencies, BGE-M3 style (token id → weight).
    """

    def __init__(self, *, dims: int = DEFAULT_DIMS, sparse: bool = True) -> None:
        self.name = f"hash-{dims}"
        self.dims = dims
        self.sparse = sparse

    def _bucket(self, token: str) -> int:
        return int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest()) % self.dims

    def _embed(self, text: str) -> Embedding:
        counts = Counter(tokenize(text))
        dense = [0.0] * self.dims
        for token, n in counts.items():
            dense[self._bucket(token)] += 1.0 + math.log(n)
        norm = math.sqrt(sum(v * v for v in dense)) or 1.0
        dense = [v / norm for v in dense]
        sparse = None
        if self.sparse and counts:
            weights: dict[int, float] = {}
            for token, n in counts.items():
                idx = self._bucket(token)
                weights[idx] = weights.get(idx, 0.0) + 1.0 + math.log(n)
            ordered = sorted(weights.items())
            sparse = SparseVector([i for i, _ in ordered], [w for _, w in ordered])
        return dense, sparse

    async def embed_documents(self, texts: Sequence[str]) -> list[Embedding]:
        return [self._embed(t) for t in texts]

    async def embed_query(self, text: str) -> Embedding:
        return self._embed(text)


class OverlapReranker:
    """Fake reranker: fraction of query terms present in the document."""

    name = "overlap"

    async def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        terms = set(tokenize(query))
        if not terms:
            return [0.0] * len(documents)
        return [len(terms & set(tokenize(doc))) / len(terms) for doc in documents]
