import json
from collections.abc import Sequence

import httpx
import pytest

from igs_common.rag import HashEmbedder, HttpEmbedder, HttpReranker, InMemoryStore, OverlapReranker
from igs_common.rag.retrieve import Retriever

from .helpers import ACCOUNT_LAKESHORE, INT_DEPOSIT, TENANT_A, TENANT_B, corpus


async def _retriever(reranker=None) -> tuple[Retriever, InMemoryStore]:
    embedder = HashEmbedder(dims=256)
    store = InMemoryStore()
    await store.upsert(await corpus(embedder))
    return Retriever(embedder=embedder, store=store, reranker=reranker), store


async def test_hybrid_retrieval_with_citations() -> None:
    retriever, _ = await _retriever(OverlapReranker())
    result = await retriever.retrieve("Who will sign the deposit?", tenant_id=TENANT_A, top_k=3)
    assert result.reranked
    top = result.hits[0]
    assert top.chunk.source_id == INT_DEPOSIT
    assert {"rerank"} <= set(top.signals)
    assert [c.n for c in result.citations] == [1, 2, 3]
    assert result.citations[0].account_id == ACCOUNT_LAKESHORE
    assert result.context().startswith("[1] Email from Robert Haines")


async def test_tenant_isolation_never_leaks() -> None:
    retriever, _ = await _retriever()
    for tenant, leaked in ((TENANT_A, "50%"), (TENANT_B, "30%")):
        result = await retriever.retrieve("deposit policy percentage", tenant_id=tenant, top_k=10)
        assert result.hits
        assert all(h.chunk.tenant_id == tenant for h in result.hits)
        assert all(leaked not in h.chunk.text for h in result.hits)


async def test_account_filter_scopes_to_one_client() -> None:
    retriever, _ = await _retriever()
    result = await retriever.retrieve(
        "deposit", tenant_id=TENANT_A, filter={"account_id": ACCOUNT_LAKESHORE}, top_k=10
    )
    assert result.hits and all(h.chunk.account_id == ACCOUNT_LAKESHORE for h in result.hits)


async def test_quarantined_chunks_are_never_returned() -> None:
    retriever, store = await _retriever()
    first = (await retriever.retrieve("visa Brazil", tenant_id=TENANT_A)).hits[0].chunk
    store.quarantined.add(first.chunk_id)
    again = await retriever.retrieve("visa Brazil", tenant_id=TENANT_A)
    assert first.chunk_id not in {h.chunk.chunk_id for h in again.hits}


class _Broken:
    name = "broken"

    async def rerank(self, query: str, documents: Sequence[str]) -> list[float]:
        raise RuntimeError("GPU cold start timeout")


async def test_reranker_failure_degrades_to_fused_order() -> None:
    retriever, _ = await _retriever(_Broken())
    result = await retriever.retrieve("deposit", tenant_id=TENANT_A, top_k=2)
    assert not result.reranked
    assert result.warnings == ["rerank failed: RuntimeError"]
    assert len(result.hits) == 2 and result.hits[0].rank == 1


async def test_delete_where_is_tenant_scoped() -> None:
    _, store = await _retriever()
    before = len(store)
    assert await store.delete_where(TENANT_B, {"source": "policy"}) == 1
    assert await store.delete_where(TENANT_B, {"source": "policy"}) == 0
    assert len(store) == before - 1


async def test_http_clients_follow_the_models_service_contract() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append({"path": request.url.path, **body})
        assert request.headers["Authorization"] == "Bearer id-token"
        if request.url.path == "/embed":
            n = len(body["texts"])
            return httpx.Response(
                200,
                json={
                    "model": "bge-m3",
                    "dense": [[0.1, 0.2, 0.3]] * n,
                    "sparse": [{"indices": [3], "values": [0.5]}] * n,
                },
            )
        return httpx.Response(
            200,
            json={
                "model": "r",
                "results": [{"index": 1, "score": 0.9}, {"index": 0, "score": 0.1}],
            },
        )

    async def auth() -> str:
        return "Bearer id-token"

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    embedder = HttpEmbedder("http://models/", dims=3, client=client, auth_header=auth)
    docs = await embedder.embed_documents([f"t{i}" for i in range(70)])
    assert len(docs) == 70 and docs[0][1] is not None and docs[0][1].indices == [3]
    assert [len(s["texts"]) for s in seen] == [64, 6]  # batched
    assert seen[0]["kind"] == "passage"
    dense, _ = await embedder.embed_query("q")
    assert dense == [0.1, 0.2, 0.3] and seen[-1]["kind"] == "query"

    reranker = HttpReranker("http://models", client=client, auth_header=auth)
    assert await reranker.rerank("q", ["a", "b"]) == [0.1, 0.9]

    bad = HttpEmbedder("http://models", dims=1024, client=client, auth_header=auth)
    with pytest.raises(ValueError, match="1024-dim"):
        await bad.embed_query("q")
