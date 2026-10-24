"""Postgres + pgvector store over `document_chunks` (default locally and the fallback in prod).

Columns this store needs on top of the phase-1 schema (added by migration 0002):

    embedding  vector(1024)   dense vector, HNSW index with vector_cosine_ops
    sparse     jsonb          {"indices": [...], "values": [...]} (BGE-M3 lexical weights)
    tsv        tsvector       GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED
    payload    jsonb          filter/store fields from `Chunk.payload()` (title, source, …)

Search runs dense (cosine, top `candidates`) and lexical (full text, OR of terms, ts_rank_cd)
in SQL, re-scores their union with the sparse dot product in Python, and fuses the three
rankings with RRF. Every statement is tenant-scoped twice: `WHERE tenant_id = :tid` and the
RLS session from `session_scope`.
"""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from igs_common.db.session import session_scope
from igs_common.rag import filters
from igs_common.rag.embed import tokenize
from igs_common.rag.store import fuse, ranked
from igs_common.rag.types import Chunk, Filter, SearchRequest, SearchResult, SparseVector

CHUNK_NAMESPACE = uuid.UUID("6f1c2a0e-6c55-4c0c-9a51-2f0f6b1d6a10")
TS_CONFIG = "simple"  # mixed EN/ES content: no stemming, same tokens on both sides

_UPSERT = text(
    """
    INSERT INTO document_chunks (
        id, tenant_id, document_id, interaction_id, account_id, ordinal, content, token_count,
        heading_path, content_hash, vector_object_id, embedding, sparse, payload
    ) VALUES (
        CAST(:id AS uuid), CAST(:tenant_id AS uuid), CAST(:document_id AS uuid),
        CAST(:interaction_id AS uuid), CAST(:account_id AS uuid), :ordinal, :content,
        :token_count, CAST(:heading_path AS text[]), :content_hash, :chunk_id,
        CAST(CAST(:embedding AS text) AS vector), CAST(:sparse AS jsonb),
        CAST(:payload AS jsonb)
    )
    ON CONFLICT (id) DO UPDATE SET
        content = EXCLUDED.content,
        token_count = EXCLUDED.token_count,
        heading_path = EXCLUDED.heading_path,
        account_id = EXCLUDED.account_id,
        embedding = EXCLUDED.embedding,
        sparse = EXCLUDED.sparse,
        payload = EXCLUDED.payload,
        updated_at = now()
    """
)

_COLUMNS = "vector_object_id, ordinal, content, token_count, payload, heading_path, sparse"


def chunk_uuid(chunk_id: str) -> uuid.UUID:
    return uuid.uuid5(CHUNK_NAMESPACE, chunk_id)


def vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(repr(float(v)) for v in values) + "]"


def ts_query(query: str) -> str | None:
    """OR of the query's words: lexical recall, ts_rank_cd decides the order."""
    words = list(dict.fromkeys(tokenize(query)))
    return " | ".join(words) if words else None


class PgVectorStore:
    def __init__(self, engine: AsyncEngine | None = None, *, role: str | None = None) -> None:
        self._engine = engine
        self._role = role

    def _scope(self, tenant_id: str):  # noqa: ANN202 - async context manager
        return session_scope(tenant_id, engine=self._engine, role=self._role)

    async def upsert(self, chunks: Sequence[Chunk]) -> None:
        by_tenant: dict[str, list[Chunk]] = defaultdict(list)
        for chunk in chunks:
            if chunk.dense is None:
                raise ValueError(f"PgVectorStore needs dense vectors ({chunk.chunk_id})")
            by_tenant[chunk.tenant_id].append(chunk)
        for tenant_id, group in by_tenant.items():
            async with self._scope(tenant_id) as session:
                await session.execute(_UPSERT, [self._row(c) for c in group])

    @staticmethod
    def _row(c: Chunk) -> dict[str, Any]:
        assert c.dense is not None
        return {
            "id": chunk_uuid(c.chunk_id),
            "tenant_id": uuid.UUID(c.tenant_id),
            "document_id": uuid.UUID(c.source_id) if c.source_kind == "document" else None,
            "interaction_id": uuid.UUID(c.source_id) if c.source_kind == "interaction" else None,
            "account_id": uuid.UUID(c.account_id) if c.account_id else None,
            "ordinal": c.ordinal,
            "content": c.text,
            "token_count": c.token_count or len(tokenize(c.text)),
            "heading_path": list(c.heading_path),
            "content_hash": c.content_hash,
            "chunk_id": c.chunk_id,
            "embedding": vector_literal(c.dense),
            "sparse": json.dumps(c.sparse.as_dict()) if c.sparse else None,
            "payload": json.dumps(c.payload()),
        }

    async def delete_where(self, tenant_id: str, filter: Filter) -> int:
        where, params = filters.to_sql(filter)
        async with self._scope(tenant_id) as session:
            result = await session.execute(
                text(
                    f"DELETE FROM document_chunks WHERE tenant_id = CAST(:tid AS uuid) AND {where}"  # noqa: S608 - fragments are allowlisted by filters.to_sql; values are bound
                ),
                {"tid": tenant_id, **params},
            )
            return result.rowcount or 0  # type: ignore[attr-defined]

    async def search(self, req: SearchRequest) -> SearchResult:
        where, params = filters.to_sql(req.filter)
        base = (
            "tenant_id = CAST(:tid AS uuid) AND NOT quarantined "
            f"AND payload IS NOT NULL AND {where}"
        )
        params = {"tid": req.tenant_id, "cand": req.candidates, **params}
        async with self._scope(req.tenant_id) as session:
            dense = await self._dense_ids(session, base, params, req.query_dense)
            lexical = await self._lexical_ids(session, base, params, req.query)
            rows = await self._rows(session, req.tenant_id, list(dict.fromkeys(dense + lexical)))
        sparse: list[str] = []
        if req.query_sparse is not None:
            scores = {
                cid: req.query_sparse.dot(sv) for cid, (_, sv) in rows.items() if sv is not None
            }
            sparse = ranked({k: v for k, v in scores.items() if v > 0}, req.candidates)
        by_id = {cid: chunk for cid, (chunk, _) in rows.items()}
        return SearchResult(hits=fuse(by_id, dense, lexical, sparse, req.top_k))

    @staticmethod
    async def _dense_ids(
        session: AsyncSession, base: str, params: dict[str, Any], vector: Sequence[float] | None
    ) -> list[str]:
        if vector is None:
            return []
        # Filtered-HNSW recall: the WHERE filter (tenant/payload/quarantine) is applied *after* the
        # HNSW graph walk, so with the default ef_search (40) a selective filter can leave far fewer
        # than :cand survivors — silently low recall. Raise ef_search for this transaction only
        # (set_config is_local=true) so enough candidates survive the filter. Scaled to :cand and
        # capped so a huge request can't blow up query time. Version-safe across pgvector ≥0.5;
        # on pgvector ≥0.8, `hnsw.iterative_scan` is the cleaner follow-up.
        ef = max(100, min(1000, int(params.get("cand", 0)) * 4))
        await session.execute(
            text("SELECT set_config('hnsw.ef_search', :ef, true)"), {"ef": str(ef)}
        )
        result = await session.execute(
            text(
                f"SELECT vector_object_id FROM document_chunks WHERE {base} "  # noqa: S608 - fragments are allowlisted by filters.to_sql; values are bound
                "AND embedding IS NOT NULL "
                "ORDER BY embedding <=> CAST(CAST(:qv AS text) AS vector) LIMIT :cand"
            ),
            {**params, "qv": vector_literal(vector)},
        )
        return [r[0] for r in result]

    @staticmethod
    async def _lexical_ids(
        session: AsyncSession, base: str, params: dict[str, Any], query: str
    ) -> list[str]:
        tsq = ts_query(query)
        if tsq is None:
            return []
        result = await session.execute(
            text(
                "SELECT vector_object_id FROM document_chunks, "  # noqa: S608 - fragments are allowlisted by filters.to_sql; values are bound
                f"to_tsquery('{TS_CONFIG}', :tsq) AS q WHERE {base} AND tsv @@ q "
                "ORDER BY ts_rank_cd(tsv, q) DESC, vector_object_id LIMIT :cand"
            ),
            {**params, "tsq": tsq},
        )
        return [r[0] for r in result]

    @staticmethod
    async def _rows(
        session: AsyncSession, tenant_id: str, ids: list[str]
    ) -> dict[str, tuple[Chunk, SparseVector | None]]:
        if not ids:
            return {}
        result = await session.execute(
            text(
                f"SELECT {_COLUMNS} FROM document_chunks "  # noqa: S608 - fragments are allowlisted by filters.to_sql; values are bound
                "WHERE tenant_id = CAST(:tid AS uuid) AND vector_object_id = ANY(:ids)"
            ),
            {"tid": tenant_id, "ids": ids},
        )
        out: dict[str, tuple[Chunk, SparseVector | None]] = {}
        for chunk_id, ordinal, content, token_count, payload, heading_path, sparse in result:
            out[chunk_id] = (
                chunk_from_payload(chunk_id, ordinal, content, token_count, payload, heading_path),
                SparseVector.from_dict(sparse),
            )
        return out


def chunk_from_payload(
    chunk_id: str,
    ordinal: int,
    content: str,
    token_count: int,
    payload: dict[str, Any],
    heading_path: Sequence[str] | None = None,
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        tenant_id=payload["tenant_id"],
        source_kind=payload["source_kind"],
        source_id=payload["source_id"],
        ordinal=ordinal,
        title=payload.get("title", ""),
        text=content,
        source=payload.get("source", ""),
        doc_type=payload.get("doc_type", ""),
        heading_path=tuple(heading_path or ()),
        account_id=payload.get("account_id"),
        page=payload.get("page"),
        gcs_uri=payload.get("gcs_uri"),
        country=payload.get("country"),
        city=payload.get("city"),
        valid_from=payload.get("valid_from"),
        valid_until=payload.get("valid_until"),
        occurred_at=payload.get("occurred_at"),
        token_count=token_count,
    )
