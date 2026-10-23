"""VertexVectorStore with fake clients: request shapes, tenant injection, response parsing."""

from typing import Any

import pytest
from google.api_core import exceptions as gexc

from igs_common.rag import HashEmbedder, VertexVectorStore
from igs_common.rag.types import SearchRequest

from .helpers import TENANT_A, TENANT_B, corpus

COLLECTION = "projects/p/locations/us-central1/collections/igs_chunks"


class FakeData:
    def __init__(self, *, conflict: bool = False) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.conflict = conflict

    async def batch_create_data_objects(self, request: Any) -> None:
        self.calls.append(("create", request))
        if self.conflict:
            raise gexc.AlreadyExists("exists")

    async def batch_update_data_objects(self, request: Any) -> None:
        self.calls.append(("update", request))

    async def batch_delete_data_objects(self, request: Any) -> None:
        self.calls.append(("delete", request))


class FakeSearch:
    def __init__(self, response: dict | None = None, pages: list[dict] | None = None) -> None:
        self.response = response or {"results": []}
        self.pages = pages or []
        self.requests: list[Any] = []

    async def batch_search_data_objects(self, request: Any) -> dict:
        self.requests.append(request)
        return self.response

    async def query_data_objects(self, request: Any) -> dict:
        self.requests.append(request)
        return self.pages.pop(0)


def _obj(chunk: Any) -> dict:
    return {
        "name": f"{COLLECTION}/dataObjects/{chunk.chunk_id}",
        "data": {**chunk.payload(), "text": chunk.text},
    }


async def test_upsert_builds_batches_and_falls_back_to_update() -> None:
    chunks = await corpus(HashEmbedder(dims=8))
    data = FakeData(conflict=True)
    store = VertexVectorStore(collection=COLLECTION, data_client=data, search_client=FakeSearch())
    await store.upsert(chunks)
    kinds = [k for k, _ in data.calls]
    assert kinds == ["create", "update"]
    create = data.calls[0][1]
    first = create["requests"][0]
    assert first["data_object_id"] == chunks[0].chunk_id
    assert first["data_object"]["data"]["tenant_id"] == TENANT_A
    assert len(first["data_object"]["vectors"]["dense"]["dense"]["values"]) == 8
    assert "sparse" in first["data_object"]["vectors"]
    updated = data.calls[1][1]["requests"][0]["data_object"]
    assert updated["name"].endswith(chunks[0].chunk_id)


async def test_search_request_injects_tenant_and_fuses() -> None:
    chunks = await corpus(HashEmbedder(dims=8))
    a = [c for c in chunks if c.tenant_id == TENANT_A]
    b = [c for c in chunks if c.tenant_id == TENANT_B]
    # one list per sub-search, plus a foreign-tenant object that must be dropped
    response = {
        "results": [
            {"results": [{"data_object": _obj(a[0])}, {"data_object": _obj(a[1])}]},
            {"results": [{"data_object": _obj(a[1])}, {"data_object": _obj(b[0])}]},
        ]
    }
    search = FakeSearch(response)
    store = VertexVectorStore(collection=COLLECTION, data_client=FakeData(), search_client=search)
    dense, sparse = await HashEmbedder(dims=8).embed_query("deposit")
    result = await store.search(
        SearchRequest(
            tenant_id=TENANT_A,
            query="deposit",
            query_dense=dense,
            query_sparse=sparse,
            filter={"source": "policy"},
            top_k=5,
        )
    )
    req = search.requests[0]
    assert [next(iter(s)) for s in req["searches"]] == [
        "vector_search",
        "text_search",
        "vector_search",
    ]
    tenant_clause = {"tenant_id": {"$eq": TENANT_A}}
    for s in req["searches"]:
        flt = next(iter(s.values()))["filter"]
        assert flt["$and"][0] == tenant_clause and {"source": {"$eq": "policy"}} in flt["$and"]
    assert req["combine"]["ranker"]["rrf"]["weights"] == [1.0, 1.0, 1.0]
    assert [h.chunk.chunk_id for h in result.hits] == [a[1].chunk_id, a[0].chunk_id]
    assert result.warnings == ["dropped a result from another tenant"]


async def test_vertex_ranker_option() -> None:
    store = VertexVectorStore(
        collection=COLLECTION,
        data_client=FakeData(),
        search_client=FakeSearch(),
        vertex_ranker=True,
    )
    req = store.build_search_request(SearchRequest(tenant_id=TENANT_A, query="q"))
    assert req["combine"]["ranker"]["vertex_ranker"]["text_record_spec"]["query"] == "q"
    assert [next(iter(s)) for s in req["searches"]] == ["text_search"]


async def test_delete_where_pages_then_deletes() -> None:
    pages = [
        {"data_objects": [{"name": "n1"}, {"name": "n2"}], "next_page_token": "p2"},
        {"data_objects": [{"name": "n3"}], "next_page_token": ""},
    ]
    data, search = FakeData(), FakeSearch(pages=pages)
    store = VertexVectorStore(collection=COLLECTION, data_client=data, search_client=search)
    assert await store.delete_where(TENANT_B, {"source": "policy"}) == 3
    assert search.requests[0]["filter"]["$and"][0] == {"tenant_id": {"$eq": TENANT_B}}
    assert search.requests[1]["page_token"] == "p2"  # noqa: S105 - pagination cursor
    assert data.calls == [
        (
            "delete",
            {"parent": COLLECTION, "requests": [{"name": "n1"}, {"name": "n2"}, {"name": "n3"}]},
        )
    ]


async def test_invalid_filter_never_reaches_the_service() -> None:
    search = FakeSearch()
    store = VertexVectorStore(collection=COLLECTION, data_client=FakeData(), search_client=search)
    with pytest.raises(ValueError):
        await store.search(SearchRequest(tenant_id=TENANT_A, query="q", filter={"tenant_id": "x"}))
    assert search.requests == []
