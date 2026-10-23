"""Query-time pipeline: embed → hybrid search (store) → rerank → citations.

    retriever = Retriever(
        embedder=HttpEmbedder(url), store=PgVectorStore(), reranker=HttpReranker(url)
    )
    result = await retriever.retrieve(
        "who signs the enrollment PO?", tenant_id=t, filter={"account_id": a}
    )
    prompt_context = result.context()      # "[1] Lakeshore > Email (2026-09-12)\n…"
    result.citations                       # what the UI links each [n] to

The tenant always comes from the caller's authenticated context, never from the model.
"""

from __future__ import annotations

import logging
from dataclasses import replace

from igs_common.rag.embed import Embedder, Reranker
from igs_common.rag.store import VectorStore
from igs_common.rag.types import Citation, Filter, Hit, RetrievalResult, SearchRequest

log = logging.getLogger(__name__)

SNIPPET_CHARS = 280


class Retriever:
    def __init__(
        self,
        *,
        embedder: Embedder,
        store: VectorStore,
        reranker: Reranker | None = None,
        candidates: int = 50,
        rerank_pool: int = 20,
    ) -> None:
        self.embedder = embedder
        self.store = store
        self.reranker = reranker
        self.candidates = candidates
        self.rerank_pool = rerank_pool

    async def retrieve(
        self,
        query: str,
        *,
        tenant_id: str,
        filter: Filter | None = None,
        top_k: int = 8,
        rerank: bool = True,
    ) -> RetrievalResult:
        dense, sparse = await self.embedder.embed_query(query)
        use_reranker = rerank and self.reranker is not None
        result = await self.store.search(
            SearchRequest(
                tenant_id=tenant_id,
                query=query,
                query_dense=dense,
                query_sparse=sparse if self.embedder.sparse else None,
                filter=filter or {},
                top_k=max(top_k, self.rerank_pool) if use_reranker else top_k,
                candidates=self.candidates,
            )
        )
        warnings = list(result.warnings)
        hits = result.hits
        reranked = False
        if use_reranker and hits:
            assert self.reranker is not None
            try:
                hits = await self._rerank(query, hits)
                reranked = True
            except Exception as exc:  # reranking is an optimization: degrade to RRF order
                log.warning("rerank failed, keeping fused order: %s", exc)
                warnings.append(f"rerank failed: {type(exc).__name__}")
        hits = [replace(h, rank=i) for i, h in enumerate(hits[:top_k], start=1)]
        return RetrievalResult(
            query=query,
            hits=hits,
            citations=[citation(i, h) for i, h in enumerate(hits, start=1)],
            reranked=reranked,
            warnings=warnings,
        )

    async def _rerank(self, query: str, hits: list[Hit]) -> list[Hit]:
        assert self.reranker is not None
        docs = [f"{h.chunk.title}\n{h.chunk.text}" for h in hits]
        scores = await self.reranker.rerank(query, docs)
        if len(scores) != len(hits):
            raise ValueError("reranker returned a different number of scores")
        scored = [
            replace(h, score=s, signals={**h.signals, "rerank": s})
            for h, s in zip(hits, scores, strict=True)
        ]
        # Stable: ties keep the fused order.
        return [h for _, h in sorted(enumerate(scored), key=lambda p: (-p[1].score, p[0]))]


def citation(n: int, hit: Hit) -> Citation:
    c = hit.chunk
    snippet = c.text if len(c.text) <= SNIPPET_CHARS else c.text[: SNIPPET_CHARS - 1] + "…"
    return Citation(
        n=n,
        chunk_id=c.chunk_id,
        source_kind=c.source_kind,
        source_id=c.source_id,
        title=c.title,
        heading_path=" > ".join(c.heading_path),
        snippet=snippet,
        account_id=c.account_id,
        page=c.page,
        gcs_uri=c.gcs_uri,
        occurred_at=c.occurred_at,
    )
