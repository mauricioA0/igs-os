"""PgVectorStore against a real Postgres + pgvector (`igs_test_w1`)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from igs_common.db.enums import AccountKind, Direction, InteractionChannel
from igs_common.db.models import Account, Document, Interaction, Tenant
from igs_common.db.session import system_scope
from igs_common.rag import HashEmbedder, OverlapReranker, PgVectorStore, Retriever
from igs_common.rag.types import SearchRequest

from .helpers import (
    ACCOUNT_LAKESHORE,
    ACCOUNT_NORTHFIELD,
    DOC_B,
    DOC_GUIDE,
    DOC_POLICY,
    INT_DEPOSIT,
    INT_NORTH,
    INT_ROSTER,
    TENANT_A,
    TENANT_B,
    corpus,
)

EMBEDDER = HashEmbedder(dims=1024)


async def _seed_sources(engine: AsyncEngine) -> None:
    U = uuid.UUID
    async with system_scope(engine=engine) as s:
        await s.execute(text("TRUNCATE tenants CASCADE"))
        s.add_all(
            [
                Tenant(id=U(TENANT_A), slug="w1-a", name="A"),
                Tenant(id=U(TENANT_B), slug="w1-b", name="B"),
            ]
        )
        await s.flush()
        for doc_id, tenant in ((DOC_POLICY, TENANT_A), (DOC_GUIDE, TENANT_A), (DOC_B, TENANT_B)):
            s.add(
                Document(
                    id=U(doc_id),
                    tenant_id=U(tenant),
                    title="doc",
                    source="policy",
                    mime_type="application/pdf",
                    content_hash=doc_id.replace("-", "").ljust(64, "0"),
                )
            )
        for acc_id, name in ((ACCOUNT_LAKESHORE, "Lakeshore"), (ACCOUNT_NORTHFIELD, "Northfield")):
            s.add(
                Account(
                    id=U(acc_id),
                    tenant_id=U(TENANT_A),
                    name=name,
                    kind=AccountKind.UNIVERSITY,
                    country="US",
                )
            )
        await s.flush()
        for int_id, acc in (
            (INT_DEPOSIT, ACCOUNT_LAKESHORE),
            (INT_ROSTER, ACCOUNT_LAKESHORE),
            (INT_NORTH, ACCOUNT_NORTHFIELD),
        ):
            s.add(
                Interaction(
                    id=U(int_id),
                    tenant_id=U(TENANT_A),
                    account_id=U(acc),
                    channel=InteractionChannel.EMAIL,
                    direction=Direction.INBOUND,
                    occurred_at=datetime(2026, 9, 12, tzinfo=UTC),
                    body="…",
                )
            )


async def _loaded_store(engine: AsyncEngine) -> PgVectorStore:
    await _seed_sources(engine)
    store = PgVectorStore(engine)
    await store.upsert(await corpus(EMBEDDER))
    return store


async def _count(engine: AsyncEngine) -> int:
    async with system_scope(engine=engine) as s:
        return (await s.execute(text("SELECT count(*) FROM document_chunks"))).scalar_one()


async def test_upsert_is_idempotent(rag_engine: AsyncEngine) -> None:
    store = await _loaded_store(rag_engine)
    first = await _count(rag_engine)
    await store.upsert(await corpus(EMBEDDER))
    assert first == await _count(rag_engine) == 7


async def test_hybrid_search_and_rerank(rag_engine: AsyncEngine) -> None:
    store = await _loaded_store(rag_engine)
    retriever = Retriever(embedder=EMBEDDER, store=store, reranker=OverlapReranker())
    result = await retriever.retrieve("Who will sign the deposit?", tenant_id=TENANT_A, top_k=3)
    assert result.hits[0].chunk.source_id == INT_DEPOSIT
    assert result.citations[0].source_kind == "interaction"
    assert result.citations[0].occurred_at == "2026-09-12T15:00:00+00:00"
    assert {"dense", "lexical"} & set(result.hits[0].signals)


async def test_lexical_signal_finds_exact_terms(rag_engine: AsyncEngine) -> None:
    store = await _loaded_store(rag_engine)
    q = "visa"
    dense, sparse = await EMBEDDER.embed_query(q)
    res = await store.search(
        SearchRequest(tenant_id=TENANT_A, query=q, query_dense=dense, query_sparse=sparse, top_k=1)
    )
    assert res.hits[0].chunk.source_id == DOC_GUIDE
    assert res.hits[0].signals.get("lexical") == 1.0


async def test_tenant_and_filters(rag_engine: AsyncEngine) -> None:
    store = await _loaded_store(rag_engine)
    retriever = Retriever(embedder=EMBEDDER, store=store)
    b = await retriever.retrieve("deposit percentage", tenant_id=TENANT_B, top_k=10)
    assert [h.chunk.source_id for h in b.hits] == [DOC_B]
    a = await retriever.retrieve("deposit percentage", tenant_id=TENANT_A, top_k=10)
    assert DOC_B not in {h.chunk.source_id for h in a.hits}

    lake = await retriever.retrieve(
        "deposit", tenant_id=TENANT_A, filter={"account_id": ACCOUNT_LAKESHORE}, top_k=10
    )
    assert lake.hits and {h.chunk.account_id for h in lake.hits} == {ACCOUNT_LAKESHORE}

    policies = await retriever.retrieve(
        "deposit",
        tenant_id=TENANT_A,
        filter={"source": {"$in": ["policy"]}, "valid_until": {"$gte": 20000}},
        top_k=10,
    )
    assert policies.hits and {h.chunk.source_id for h in policies.hits} == {DOC_POLICY}


async def test_quarantine_and_delete(rag_engine: AsyncEngine) -> None:
    store = await _loaded_store(rag_engine)
    async with system_scope(engine=rag_engine) as s:
        await s.execute(
            text("UPDATE document_chunks SET quarantined = true WHERE interaction_id = :i"),
            {"i": uuid.UUID(INT_DEPOSIT)},
        )
    retriever = Retriever(embedder=EMBEDDER, store=store)
    result = await retriever.retrieve("sign the deposit", tenant_id=TENANT_A, top_k=10)
    assert INT_DEPOSIT not in {h.chunk.source_id for h in result.hits}

    assert await store.delete_where(TENANT_A, {"account_id": ACCOUNT_LAKESHORE}) == 2
    assert await store.delete_where(TENANT_B, {"account_id": ACCOUNT_NORTHFIELD}) == 0
    assert await _count(rag_engine) == 5
