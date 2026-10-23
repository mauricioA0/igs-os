"""Run ingestion without Temporal — the same steps the worker activities run, in-process.

Used by the seed / demo reset (``python -m igs_common.ingest index-interactions``) and by tests.
Production goes through the ``IngestDocument`` / ``IndexInteractions`` workflows so long jobs
are retried and resumable; both paths call the same ``pipeline`` functions.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine

from igs_common.db.session import session_scope
from igs_common.rag.embed import Embedder
from igs_common.rag.store import VectorStore

from . import pipeline
from .chunking import ChunkingConfig

EMBED_BATCH = 64
PAGE_SIZE = 200


@dataclass(slots=True)
class IndexStats:
    sources: int = 0
    chunks: int = 0
    indexed: int = 0
    quarantined: int = 0
    cleared: int = 0
    skipped: int = 0


def scope_for(tenant_id: str, engine: AsyncEngine | None = None) -> pipeline.SessionScope:
    return lambda: session_scope(tenant_id, engine=engine)


async def ingest_document(
    *,
    tenant_id: str,
    document_id: str,
    embedder: Embedder,
    store: VectorStore,
    engine: AsyncEngine | None = None,
    loader: pipeline.ContentLoader | None = None,
    config: ChunkingConfig | None = None,
    force: bool = False,
) -> IndexStats:
    scope = scope_for(tenant_id, engine)
    prepared = await pipeline.prepare_document(
        scope,
        store,
        tenant_id=tenant_id,
        document_id=document_id,
        loader=loader,
        config=config,
        force=force,
    )
    stats = IndexStats(
        sources=1,
        chunks=prepared.chunks,
        quarantined=prepared.quarantined,
        cleared=prepared.cleared,
        skipped=int(prepared.unchanged),
    )
    if prepared.unchanged:
        return stats
    try:
        for start in range(0, len(prepared.chunk_ids), EMBED_BATCH):
            stats.indexed += await pipeline.index_batch(
                scope,
                tenant_id=tenant_id,
                chunk_ids=prepared.chunk_ids[start : start + EMBED_BATCH],
                embedder=embedder,
                store=store,
            )
    except Exception as exc:
        async with scope() as session:
            await pipeline.fail_document(
                session, document_id=document_id, job_id=prepared.job_id, error=repr(exc)
            )
        raise
    async with scope() as session:
        await pipeline.finish_document(
            session,
            document_id=document_id,
            job_id=prepared.job_id,
            indexed=stats.indexed,
            embedding_model=embedder.name,
        )
    return stats


async def index_interactions(
    *,
    tenant_id: str,
    embedder: Embedder,
    store: VectorStore,
    engine: AsyncEngine | None = None,
    account_id: str | None = None,
    config: ChunkingConfig | None = None,
    force: bool = False,
) -> IndexStats:
    """Index every interaction of a tenant (or one account) for Account 360 retrieval."""
    scope = scope_for(tenant_id, engine)
    stats = IndexStats()
    after: str | None = None
    while True:
        async with scope() as session:
            ids = await pipeline.list_interaction_ids(
                session, tenant_id=tenant_id, account_id=account_id, after=after, limit=PAGE_SIZE
            )
        if not ids:
            return stats
        prepared = await pipeline.prepare_interactions(
            scope, store, tenant_id=tenant_id, interaction_ids=ids, config=config, force=force
        )
        stats.sources += prepared.sources
        stats.chunks += prepared.chunks
        stats.quarantined += prepared.quarantined
        stats.cleared += prepared.cleared
        for start in range(0, len(prepared.chunk_ids), EMBED_BATCH):
            stats.indexed += await pipeline.index_batch(
                scope,
                tenant_id=tenant_id,
                chunk_ids=prepared.chunk_ids[start : start + EMBED_BATCH],
                embedder=embedder,
                store=store,
            )
        after = ids[-1]


def default_embedder() -> Embedder:
    """Same wiring as retrieval: see ``igs_common.rag.defaults``."""
    from igs_common.rag.defaults import default_embedder as rag_default_embedder

    return rag_default_embedder()


def default_store(engine: AsyncEngine | None = None) -> VectorStore:
    """pgvector (``document_chunks``) unless ``IGS_VECTOR_STORE=vertex`` — Vertex needs its own
    client wiring (owned by ``igs_common.rag``)."""
    from igs_common.rag.pgvector_store import PgVectorStore

    backend = os.environ.get("IGS_VECTOR_STORE", "pgvector")
    if backend != "pgvector":
        raise NotImplementedError(f"IGS_VECTOR_STORE={backend!r}: build it via igs_common.rag")
    return PgVectorStore(engine)
