"""Ingestion activities: thin wrappers over ``igs_common.ingest.pipeline``.

Activities carry ids, never chunk text: text lives in Postgres and the vector store, so Temporal
history stays small and coach/client content never sits in it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine
from temporalio import activity
from temporalio.exceptions import ApplicationError

from igs_common.db.session import configure, session_scope
from igs_common.ingest import pipeline
from igs_common.ingest.parsers import UnsupportedFormatError
from igs_common.rag.embed import Embedder
from igs_common.rag.store import VectorStore


@dataclass
class PrepareDocumentInput:
    tenant_id: str
    document_id: str
    force: bool = False


@dataclass
class ListInteractionsInput:
    tenant_id: str
    account_id: str | None = None
    after: str | None = None
    limit: int = 100


@dataclass
class PrepareInteractionsInput:
    tenant_id: str
    interaction_ids: list[str]
    force: bool = False


@dataclass
class IndexBatchInput:
    tenant_id: str
    chunk_ids: list[str]


@dataclass
class FinishDocumentInput:
    tenant_id: str
    document_id: str
    job_id: str | None
    indexed: int
    embedding_model: str | None = None


@dataclass
class FailDocumentInput:
    tenant_id: str
    document_id: str
    job_id: str | None
    error: str


@dataclass
class PreparedRefs:
    chunk_ids: list[str] = field(default_factory=list)
    unchanged: bool = False
    sources: int = 0
    chunks: int = 0
    quarantined: int = 0
    cleared: int = 0
    job_id: str | None = None
    hidden_text: bool = False

    @classmethod
    def of(cls, p: pipeline.PreparedSource) -> PreparedRefs:
        return cls(
            chunk_ids=list(p.chunk_ids),
            unchanged=p.unchanged,
            sources=p.sources,
            chunks=p.chunks,
            quarantined=p.quarantined,
            cleared=p.cleared,
            job_id=p.job_id,
            hidden_text=p.hidden_text,
        )


@dataclass
class IndexBatchResult:
    indexed: int
    embedding_model: str


class IngestionActivities:
    """Dependencies are built lazily on first use so importing the worker needs no DB/network.

    Tests inject an engine, an embedder and a store (``HashEmbedder`` / ``InMemoryStore``).
    """

    def __init__(
        self,
        *,
        engine: AsyncEngine | None = None,
        embedder: Embedder | None = None,
        store: VectorStore | None = None,
        loader: pipeline.ContentLoader | None = None,
        store_factory: Callable[[AsyncEngine | None], VectorStore] | None = None,
        embedder_factory: Callable[[], Embedder] | None = None,
    ) -> None:
        self._engine = engine
        self._embedder = embedder
        self._store = store
        self._loader = loader
        self._store_factory = store_factory
        self._embedder_factory = embedder_factory

    # ── dependency resolution ──

    def _engine_or_default(self) -> AsyncEngine:
        if self._engine is None:
            self._engine = configure()
        return self._engine

    def _get_embedder(self) -> Embedder:
        if self._embedder is None:
            from igs_common.ingest.runner import default_embedder

            self._embedder = (self._embedder_factory or default_embedder)()
        return self._embedder

    def _get_store(self) -> VectorStore:
        if self._store is None:
            from igs_common.ingest.runner import default_store

            self._store = (self._store_factory or default_store)(self._engine_or_default())
        return self._store

    def _scope(self, tenant_id: str) -> pipeline.SessionScope:
        engine = self._engine_or_default()
        return lambda: session_scope(tenant_id, engine=engine)

    # ── activities ──

    @activity.defn(name="ingest.prepare_document")
    async def prepare_document(self, inp: PrepareDocumentInput) -> PreparedRefs:
        try:
            prepared = await pipeline.prepare_document(
                self._scope(inp.tenant_id),
                self._get_store(),
                tenant_id=inp.tenant_id,
                document_id=inp.document_id,
                loader=self._loader,
                force=inp.force,
            )
        except (LookupError, UnsupportedFormatError, ValueError) as exc:
            raise ApplicationError(str(exc), type="validation", non_retryable=True) from exc
        return PreparedRefs.of(prepared)

    @activity.defn(name="ingest.list_interactions")
    async def list_interactions(self, inp: ListInteractionsInput) -> list[str]:
        async with self._scope(inp.tenant_id)() as session:
            return await pipeline.list_interaction_ids(
                session,
                tenant_id=inp.tenant_id,
                account_id=inp.account_id,
                after=inp.after,
                limit=inp.limit,
            )

    @activity.defn(name="ingest.prepare_interactions")
    async def prepare_interactions(self, inp: PrepareInteractionsInput) -> PreparedRefs:
        prepared = await pipeline.prepare_interactions(
            self._scope(inp.tenant_id),
            self._get_store(),
            tenant_id=inp.tenant_id,
            interaction_ids=inp.interaction_ids,
            force=inp.force,
        )
        return PreparedRefs.of(prepared)

    @activity.defn(name="ingest.index_batch")
    async def index_batch(self, inp: IndexBatchInput) -> IndexBatchResult:
        embedder = self._get_embedder()
        indexed = await pipeline.index_batch(
            self._scope(inp.tenant_id),
            tenant_id=inp.tenant_id,
            chunk_ids=inp.chunk_ids,
            embedder=embedder,
            store=self._get_store(),
        )
        return IndexBatchResult(indexed=indexed, embedding_model=embedder.name)

    @activity.defn(name="ingest.finish_document")
    async def finish_document(self, inp: FinishDocumentInput) -> None:
        async with self._scope(inp.tenant_id)() as session:
            await pipeline.finish_document(
                session,
                document_id=inp.document_id,
                job_id=inp.job_id,
                indexed=inp.indexed,
                embedding_model=inp.embedding_model,
            )

    @activity.defn(name="ingest.fail_document")
    async def fail_document(self, inp: FailDocumentInput) -> None:
        async with self._scope(inp.tenant_id)() as session:
            await pipeline.fail_document(
                session, document_id=inp.document_id, job_id=inp.job_id, error=inp.error
            )

    def all(self) -> list[Callable[..., Any]]:
        return [
            self.prepare_document,
            self.list_interactions,
            self.prepare_interactions,
            self.index_batch,
            self.finish_document,
            self.fail_document,
        ]
