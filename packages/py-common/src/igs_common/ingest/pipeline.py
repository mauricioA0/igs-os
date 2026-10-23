"""Ingestion steps that touch Postgres and the vector store, split so Temporal can run each as an
activity and retry it independently:

1. ``prepare_document`` / ``prepare_interactions`` — load, parse, chunk, quarantine-check and
   write ``document_chunks`` rows (Postgres is the source of truth for chunk text). Sources whose
   content changed are first cleared from the vector store. Unchanged sources are skipped.
2. ``index_batch`` — embed a batch of chunk rows, upsert them into the ``VectorStore`` and mark
   them indexed. Quarantined chunks are never indexed; clearing one in review and re-running
   ingestion indexes it.
3. ``finish_document`` / ``fail_document`` — status, counts and the ``ingestion_jobs`` row.

Ids line up with ``igs_common.rag``: a chunk's store id is ``make_chunk_id(...)`` (content
addressed) and its row id is ``chunk_uuid(store id)``, the same row ``PgVectorStore`` upserts
into. Re-running any step after a crash rewrites the same ids. ``vector_object_id`` is set only
once the store accepted the chunk, so it doubles as the "indexed" marker.

Tenant isolation: every DB step runs in ``session_scope(tenant_id)`` (RLS); stores add the
tenant filter themselves.
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from igs_common.db.enums import DocumentStatus, IngestionStatus
from igs_common.db.models import (
    Account,
    Document,
    DocumentChunk,
    IngestionJob,
    Interaction,
    Stakeholder,
)
from igs_common.rag.embed import Embedder
from igs_common.rag.pgvector_store import chunk_uuid
from igs_common.rag.store import VectorStore
from igs_common.rag.types import Chunk as VectorChunk
from igs_common.rag.types import SourceKind, make_chunk_id

from .chunking import ChunkingConfig, chunk_document
from .hashing import bytes_hash
from .parsers import parse_bytes, parse_interaction
from .types import Chunk, ParsedDocument

# Opens one tenant-scoped transaction: ``lambda: session_scope(tenant_id, engine=...)``.
SessionScope = Callable[[], AbstractAsyncContextManager[AsyncSession]]

_DOC_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/html": "html",
    "text/markdown": "text",
    "text/plain": "text",
}


class ContentLoader(Protocol):
    """Fetches a document's original bytes (GCS in production)."""

    async def load(self, uri: str) -> bytes: ...


class LocalFileLoader:
    """``file://`` URIs only — local dev and tests. Production injects a GCS loader."""

    async def load(self, uri: str) -> bytes:
        if not uri.startswith("file://"):
            raise NotImplementedError(f"no loader configured for {uri.split(':', 1)[0]}:// URIs")
        path = Path(uri.removeprefix("file://"))
        return await asyncio.to_thread(path.read_bytes)


@dataclass(slots=True)
class PreparedSource:
    """Result of a prepare step: what the workflow has to index next (ids only, small payload)."""

    chunk_ids: list[str] = field(default_factory=list)  # document_chunks.id to (re)index
    unchanged: bool = False
    sources: int = 0
    chunks: int = 0
    quarantined: int = 0
    cleared: int = 0  # store entries removed because their source changed
    job_id: str | None = None
    hidden_text: bool = False


def store_id(
    tenant_id: str, kind: SourceKind, source_id: uuid.UUID | str, c_ordinal: int, text: str
) -> str:
    return make_chunk_id(tenant_id, kind, str(source_id), c_ordinal, text)


def row_hash(ordinal: int, text: str) -> str:
    """Same formula as ``igs_common.rag.types.Chunk.content_hash`` (what the store writes)."""
    return hashlib.sha256(f"{ordinal}\x1f{text}".encode()).hexdigest()


# ── Documents ─────────────────────────────────────────────────────────────


async def prepare_document(
    scope: SessionScope,
    store: VectorStore,
    *,
    tenant_id: str,
    document_id: str,
    loader: ContentLoader | None = None,
    config: ChunkingConfig | None = None,
    force: bool = False,
) -> PreparedSource:
    async with scope() as session:
        doc = await session.get(Document, uuid.UUID(document_id))
        if doc is None or doc.tenant_id != uuid.UUID(tenant_id):
            raise LookupError(f"document {document_id} not found")
        data = await _document_bytes(doc, loader or LocalFileLoader())
        digest = bytes_hash(data)
        existing = await _existing_chunks(session, document_id=doc.id)
        indexed = [r for r in existing if r.vector_object_id]
        if (
            not force
            and doc.status == DocumentStatus.READY
            and doc.content_hash == digest
            and existing
            and all(r.vector_object_id or r.quarantined for r in existing)
        ):
            return PreparedSource(unchanged=True, sources=1, chunks=len(existing))
        title, mime = doc.title, doc.mime_type

    parsed = parse_bytes(data, mime, title=title)
    chunks = _dedupe(chunk_document(parsed, config))
    # Content changed (or forced): drop what the store holds for this document before the rows
    # are rewritten. With PgVectorStore this also deletes the rows; they're recreated below.
    cleared = await store.delete_where(tenant_id, {"source_id": document_id}) if indexed else 0

    async with scope() as session:
        doc = await session.get(Document, uuid.UUID(document_id))
        assert doc is not None
        job = IngestionJob(
            tenant_id=uuid.UUID(tenant_id), document_id=doc.id, status=IngestionStatus.EMBEDDING
        )
        session.add(job)
        prepared = await _sync_rows(
            session,
            tenant_id=tenant_id,
            kind="document",
            source_id=doc.id,
            chunks=chunks,
            row_fields={"document_id": doc.id},
            reindex_all=bool(indexed),
        )
        await session.flush()
        doc.status = DocumentStatus.INGESTING
        doc.content_hash = digest
        doc.current_job_id = job.id
        job.stats = {
            "chunks": prepared.chunks,
            "quarantined": prepared.quarantined,
            "hidden_text": bool(parsed.metadata.get("hidden_text")),
        }
        prepared.job_id = str(job.id)
    prepared.cleared = cleared
    prepared.hidden_text = bool(parsed.metadata.get("hidden_text"))
    return prepared


async def _document_bytes(doc: Document, loader: ContentLoader) -> bytes:
    inline = getattr(doc, "inline_content", None) or (doc.metadata_ or {}).get("inline_content")
    if inline:
        return str(inline).encode("utf-8")
    if not doc.gcs_uri:
        raise ValueError(f"document {doc.id} has no content (no inline_content and no gcs_uri)")
    return await loader.load(doc.gcs_uri)


async def finish_document(
    session: AsyncSession,
    *,
    document_id: str,
    job_id: str | None,
    indexed: int,
    embedding_model: str | None,
) -> None:
    doc = await session.get(Document, uuid.UUID(document_id))
    if doc is None:
        raise LookupError(f"document {document_id} not found")
    chunk_count = len(await _existing_chunks(session, document_id=doc.id))
    doc.status = DocumentStatus.READY
    doc.chunk_count = chunk_count
    if embedding_model:
        doc.embedding_model = embedding_model
    if job_id:
        job = await session.get(IngestionJob, uuid.UUID(job_id))
        if job is not None:
            job.status = IngestionStatus.SUCCEEDED
            job.embedding_model = embedding_model
            job.stats = {**(job.stats or {}), "indexed": indexed, "chunks": chunk_count}
            job.finished_at = datetime.now(UTC)


async def fail_document(
    session: AsyncSession, *, document_id: str, job_id: str | None, error: str
) -> None:
    doc = await session.get(Document, uuid.UUID(document_id))
    if doc is not None:
        doc.status = DocumentStatus.FAILED
    if job_id:
        job = await session.get(IngestionJob, uuid.UUID(job_id))
        if job is not None:
            job.status = IngestionStatus.FAILED
            job.error = error[:2000]
            job.finished_at = datetime.now(UTC)


# ── Interactions (Account 360) ────────────────────────────────────────────


async def list_interaction_ids(
    session: AsyncSession,
    *,
    tenant_id: str,
    account_id: str | None = None,
    after: str | None = None,
    limit: int = 200,
) -> list[str]:
    """Stable keyset paging by id (UUIDv7 ⇒ roughly creation order).

    Filters by tenant explicitly on top of RLS: the owner connection (local dev, system jobs)
    bypasses RLS, and indexing another tenant's interactions must be impossible either way."""
    stmt = (
        select(Interaction.id)
        .where(Interaction.tenant_id == uuid.UUID(tenant_id))
        .order_by(Interaction.id)
        .limit(limit)
    )
    if account_id:
        stmt = stmt.where(Interaction.account_id == uuid.UUID(account_id))
    if after:
        stmt = stmt.where(Interaction.id > uuid.UUID(after))
    return [str(i) for i in (await session.scalars(stmt)).all()]


@dataclass(slots=True)
class _InteractionPlan:
    interaction_id: uuid.UUID
    account_id: uuid.UUID
    parsed: ParsedDocument
    chunks: list[Chunk]
    changed: bool  # rows must be (re)written or (re)indexed
    must_clear: bool  # the store holds chunks that no longer exist


async def prepare_interactions(
    scope: SessionScope,
    store: VectorStore,
    *,
    tenant_id: str,
    interaction_ids: Sequence[str],
    config: ChunkingConfig | None = None,
    force: bool = False,
) -> PreparedSource:
    plans: list[_InteractionPlan] = []
    async with scope() as session:
        rows = (
            await session.execute(
                select(Interaction, Account.name, Stakeholder.name)
                .join(Account, Account.id == Interaction.account_id)
                .outerjoin(Stakeholder, Stakeholder.id == Interaction.stakeholder_id)
                .where(Interaction.tenant_id == uuid.UUID(tenant_id))
                .where(Interaction.id.in_([uuid.UUID(i) for i in interaction_ids]))
                .order_by(Interaction.id)
            )
        ).all()
        for interaction, account_name, stakeholder_name in rows:
            parsed = parse_interaction(
                channel=str(interaction.channel),
                direction=str(interaction.direction),
                occurred_at=interaction.occurred_at,
                subject=interaction.subject,
                body=interaction.body,
                account_name=account_name,
                stakeholder=stakeholder_name,
            )
            chunks = _dedupe(chunk_document(parsed, config))
            existing = await _existing_chunks(session, interaction_id=interaction.id)
            wanted = {
                store_id(tenant_id, "interaction", interaction.id, c.ordinal, c.text)
                for c in chunks
            }
            have = {
                store_id(tenant_id, "interaction", interaction.id, r.ordinal, r.content)
                for r in existing
            }
            complete = all(r.vector_object_id or r.quarantined for r in existing)
            plans.append(
                _InteractionPlan(
                    interaction_id=interaction.id,
                    account_id=interaction.account_id,
                    parsed=parsed,
                    chunks=chunks,
                    changed=force or wanted != have or not complete,
                    # A run that only failed to finish indexing re-upserts the same ids
                    # (idempotent); the store is cleared only when the chunk set changed.
                    must_clear=(force or wanted != have)
                    and any(r.vector_object_id for r in existing),
                )
            )

    total = PreparedSource(sources=len(plans))
    for plan in plans:
        if plan.must_clear:
            total.cleared += await store.delete_where(
                tenant_id, {"source_id": str(plan.interaction_id)}
            )

    async with scope() as session:
        for plan in plans:
            total.chunks += len(plan.chunks)
            total.quarantined += sum(1 for c in plan.chunks if c.quarantined)
            if not plan.changed:
                continue
            prepared = await _sync_rows(
                session,
                tenant_id=tenant_id,
                kind="interaction",
                source_id=plan.interaction_id,
                chunks=plan.chunks,
                row_fields={
                    "interaction_id": plan.interaction_id,
                    "account_id": plan.account_id,
                },
                reindex_all=plan.must_clear,
            )
            total.chunk_ids += prepared.chunk_ids
    total.unchanged = not total.chunk_ids and not total.cleared
    return total


# ── Shared chunk-row sync ─────────────────────────────────────────────────


def _dedupe(chunks: list[Chunk]) -> list[Chunk]:
    """Identical text twice in one source (repeated footer…) is indexed once."""
    seen: set[str] = set()
    out: list[Chunk] = []
    for c in chunks:
        if c.content_hash not in seen:
            seen.add(c.content_hash)
            out.append(c)
    return out


async def _existing_chunks(
    session: AsyncSession,
    *,
    document_id: uuid.UUID | None = None,
    interaction_id: uuid.UUID | None = None,
) -> list[DocumentChunk]:
    stmt = select(DocumentChunk)
    if document_id is not None:
        stmt = stmt.where(DocumentChunk.document_id == document_id)
    else:
        stmt = stmt.where(DocumentChunk.interaction_id == interaction_id)
    return list((await session.scalars(stmt.order_by(DocumentChunk.ordinal))).all())


async def _sync_rows(
    session: AsyncSession,
    *,
    tenant_id: str,
    kind: SourceKind,
    source_id: uuid.UUID,
    chunks: list[Chunk],
    row_fields: dict[str, Any],
    reindex_all: bool = False,
) -> PreparedSource:
    """Make the source's rows match ``chunks``: delete rows that are gone, insert new ones,
    keep identical ones (and their review state). Returns the rows still to index.

    ``reindex_all``: the store was cleared for this source, so every kept row loses its
    "indexed" marker (stores that live outside Postgres still have the rows here)."""
    existing = await _existing_chunks(
        session,
        document_id=source_id if kind == "document" else None,
        interaction_id=source_id if kind == "interaction" else None,
    )
    wanted = {
        chunk_uuid(store_id(tenant_id, kind, source_id, c.ordinal, c.text)): c for c in chunks
    }
    stale = [r.id for r in existing if r.id not in wanted]
    if stale:
        await session.execute(delete(DocumentChunk).where(DocumentChunk.id.in_(stale)))
        await session.flush()
    have = {r.id: r for r in existing if r.id in wanted}

    now = datetime.now(UTC)
    to_index: list[str] = []
    for row_id, chunk in wanted.items():
        row = have.get(row_id)
        if row is None:
            row = DocumentChunk(
                id=row_id,
                tenant_id=uuid.UUID(tenant_id),
                ordinal=chunk.ordinal,
                content=chunk.text,
                token_count=chunk.token_count,
                heading_path=list(chunk.heading_path),
                content_hash=row_hash(chunk.ordinal, chunk.text),
                quarantined=chunk.quarantined,
                quarantine_reason=chunk.quarantine_reason,
                quarantined_at=now if chunk.quarantined else None,
                **row_fields,
            )
            session.add(row)
        elif reindex_all:
            row.vector_object_id = None
        if chunk.quarantined and not row.quarantined and row.reviewed_at is None:
            # Heuristics got stricter since the last run: pull it out of retrieval.
            row.quarantined = True
            row.quarantine_reason = chunk.quarantine_reason
            row.quarantined_at = now
        if not row.quarantined and not row.vector_object_id:
            to_index.append(str(row_id))
    await session.flush()
    return PreparedSource(
        chunk_ids=to_index,
        sources=1,
        chunks=len(wanted),
        quarantined=sum(1 for c in chunks if c.quarantined),
    )


# ── Indexing ──────────────────────────────────────────────────────────────


async def load_vector_chunks(
    session: AsyncSession, *, tenant_id: str, chunk_ids: Sequence[str]
) -> list[VectorChunk]:
    """Rebuild store-ready chunks (text + payload) from Postgres for a batch of chunk rows."""
    rows = (
        await session.execute(
            select(DocumentChunk, Document, Interaction)
            .outerjoin(Document, Document.id == DocumentChunk.document_id)
            .outerjoin(Interaction, Interaction.id == DocumentChunk.interaction_id)
            .where(DocumentChunk.tenant_id == uuid.UUID(tenant_id))
            .where(DocumentChunk.id.in_([uuid.UUID(i) for i in chunk_ids]))
            .where(DocumentChunk.quarantined.is_(False))
            .order_by(DocumentChunk.id)
        )
    ).all()
    out: list[VectorChunk] = []
    for chunk, doc, interaction in rows:
        heading = tuple(chunk.heading_path or ())
        if doc is not None:
            meta = doc.metadata_ or {}
            out.append(
                VectorChunk(
                    chunk_id=store_id(tenant_id, "document", doc.id, chunk.ordinal, chunk.content),
                    tenant_id=tenant_id,
                    source_kind="document",
                    source_id=str(doc.id),
                    ordinal=chunk.ordinal,
                    title=doc.title,
                    text=chunk.content,
                    source=doc.source,
                    doc_type=_DOC_TYPES.get(doc.mime_type.split(";")[0].strip(), "text"),
                    heading_path=heading,
                    page=_page(heading),
                    gcs_uri=doc.gcs_uri,
                    country=meta.get("country"),
                    city=meta.get("city"),
                    token_count=chunk.token_count,
                )
            )
        elif interaction is not None:
            out.append(
                VectorChunk(
                    chunk_id=store_id(
                        tenant_id, "interaction", interaction.id, chunk.ordinal, chunk.content
                    ),
                    tenant_id=tenant_id,
                    source_kind="interaction",
                    source_id=str(interaction.id),
                    ordinal=chunk.ordinal,
                    title=interaction.subject or (heading[0] if heading else "Interaction"),
                    text=chunk.content,
                    source=str(interaction.channel),
                    doc_type="interaction",
                    heading_path=heading,
                    account_id=str(interaction.account_id),
                    occurred_at=interaction.occurred_at.isoformat(),
                    token_count=chunk.token_count,
                )
            )
    return out


def _page(heading: tuple[str, ...]) -> int | None:
    if heading and heading[0].startswith("Page "):
        tail = heading[0].removeprefix("Page ")
        return int(tail) if tail.isdigit() else None
    return None


async def index_batch(
    scope: SessionScope,
    *,
    tenant_id: str,
    chunk_ids: Sequence[str],
    embedder: Embedder,
    store: VectorStore,
) -> int:
    """Embed + upsert one batch of rows, then mark them indexed. Idempotent."""
    async with scope() as session:
        chunks = await load_vector_chunks(session, tenant_id=tenant_id, chunk_ids=chunk_ids)
    if not chunks:
        return 0
    vectors = await embedder.embed_documents([c.text for c in chunks])
    if len(vectors) != len(chunks):
        raise RuntimeError(f"embedder returned {len(vectors)} vectors for {len(chunks)} texts")
    await store.upsert(
        [replace(c, dense=d, sparse=s) for c, (d, s) in zip(chunks, vectors, strict=True)]
    )
    async with scope() as session:
        for c in chunks:
            await session.execute(
                update(DocumentChunk)
                .where(DocumentChunk.id == chunk_uuid(c.chunk_id))
                .values(vector_object_id=c.chunk_id)
            )
    return len(chunks)
