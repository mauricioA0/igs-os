"""Process-wide retrieval wiring from the environment.

``IGS_MODELS_URL`` → BGE-M3 + bge-reranker-v2-m3 served by ``services/models``; without it the
deterministic hash embedder is used (dev and tests only). ``IGS_VECTOR_STORE`` selects the
store (``pgvector`` today; Vertex is wired by deployment code, not here).
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from collections.abc import Awaitable, Callable
from functools import cache
from uuid import UUID

from igs_common.rag.embed import Embedder, HashEmbedder, HttpEmbedder, HttpReranker, Reranker
from igs_common.rag.pgvector_store import PgVectorStore
from igs_common.rag.retrieve import Retriever
from igs_common.rag.store import VectorStore
from igs_common.rag.types import Filter, Hit

JSON = dict[str, object]


def cloud_run_auth(url: str) -> Callable[[], Awaitable[str | None]] | None:
    """`Authorization: Bearer <ID token>` for a private Cloud Run service (audience = its URL).

    Uses Application Default Credentials (metadata server on Cloud Run / GKE Workload Identity).
    Tokens live ~1h; cached and refreshed 5 minutes before expiry. Plain http URLs (local
    development) get no header.
    """
    if not url.startswith("https://"):
        return None
    cached: dict[str, object] = {"token": None, "exp": 0.0}

    def fetch() -> str:
        import google.auth.transport.requests
        import google.oauth2.id_token

        token = google.oauth2.id_token.fetch_id_token(google.auth.transport.requests.Request(), url)
        if not token:
            raise RuntimeError(f"no ID token for {url} (Application Default Credentials?)")
        return str(token)

    async def header() -> str | None:
        if cached["token"] is None or time.monotonic() > float(cached["exp"]):  # type: ignore[arg-type]
            cached["token"] = await asyncio.to_thread(fetch)
            cached["exp"] = time.monotonic() + 55 * 60
        return f"Bearer {cached['token']}"

    return header


def _models_timeout() -> float:
    # The models service scales to zero and loads ~4.5 GB of weights on a cold start.
    return float(os.environ.get("IGS_MODELS_TIMEOUT", "30"))


def default_embedder() -> Embedder:
    url = os.environ.get("IGS_MODELS_URL")
    if not url:
        return HashEmbedder()
    return HttpEmbedder(url, timeout=_models_timeout(), auth_header=cloud_run_auth(url))


def default_reranker() -> Reranker | None:
    url = os.environ.get("IGS_MODELS_URL")
    if not url:
        return None
    return HttpReranker(url, timeout=_models_timeout(), auth_header=cloud_run_auth(url))


def default_store() -> VectorStore:
    backend = os.environ.get("IGS_VECTOR_STORE", "pgvector")
    if backend != "pgvector":
        raise NotImplementedError(f"IGS_VECTOR_STORE={backend!r} is wired by deployment code")
    return PgVectorStore()


@cache
def default_retriever() -> Retriever:
    return Retriever(
        embedder=default_embedder(), store=default_store(), reranker=default_reranker()
    )


async def retrieve(
    query: str, *, tenant_id: str, filters: Filter | None = None, k: int = 8
) -> list[Hit]:
    """Hybrid search + rerank for one tenant; the tenant filter is always injected."""
    result = await default_retriever().retrieve(query, tenant_id=tenant_id, filter=filters, top_k=k)
    return list(result.hits)


async def search_knowledge(tenant_id: UUID, query: str, k: int) -> list[JSON]:
    """Knowledge-base passages (documents only) shaped for agent tools, with citations."""
    result = await default_retriever().retrieve(
        query,
        tenant_id=str(tenant_id),
        filter={"source_kind": {"$eq": "document"}},
        top_k=k,
    )
    return [
        {
            "n": c.n,
            # Readable, stable id the agent quotes as [citation] (the tool tells it to).
            "citation": _slug(c.title) or c.source_id,
            "title": c.title,
            "section": c.heading_path,
            "snippet": c.snippet,
            "source_id": c.source_id,
        }
        for c in result.citations
    ]


def _slug(title: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")
