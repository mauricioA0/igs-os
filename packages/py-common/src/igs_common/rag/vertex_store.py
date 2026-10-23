"""Vertex AI Vector Search 2.0 ("Agent Retrieval") store, behind the same `VectorStore` protocol.

Uses the async clients of `google-cloud-vectorsearch` (`vectorsearch_v1`, beta on PyPI — pinned).
Clients are injected so tests run with fakes and no GCP calls. One collection for all tenants;
the tenant clause is always added by `filters.with_tenant`.

Collection setup (filter fields are fixed at index creation, see rag.md §2): filterable
`tenant_id, account_id, source_kind, source_id, source, doc_type, country, city, valid_from,
valid_until`; vector fields `dense` (+ `sparse` when the embedder emits it).

Not verified against the live service yet (IGS_RAG_LIVE contract test pending): the shape of
the combined result when `combine` is set. The parser accepts one fused list or one list per
search (fused locally with RRF).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from igs_common.rag import filters
from igs_common.rag.fusion import rrf
from igs_common.rag.types import Chunk, Filter, Hit, SearchRequest, SearchResult, SparseVector

BATCH_LIMIT = 1000  # service limit per batch write (atomic)
VERTEX_RANKER_MODEL = "semantic-ranker-default-004"


class DataObjectClient(Protocol):
    async def batch_create_data_objects(self, request: Any) -> Any: ...
    async def batch_update_data_objects(self, request: Any) -> Any: ...
    async def batch_delete_data_objects(self, request: Any) -> Any: ...


class SearchClient(Protocol):
    async def batch_search_data_objects(self, request: Any) -> Any: ...
    async def query_data_objects(self, request: Any) -> Any: ...


def _as_mapping(obj: Any) -> Any:
    """proto-plus messages → plain dicts (fakes already return dicts)."""
    if isinstance(obj, Mapping | list | str | int | float | bool) or obj is None:
        return obj
    to_dict = getattr(type(obj), "to_dict", None)
    if to_dict is not None:
        return to_dict(obj, preserving_proto_field_name=True)
    return obj


class VertexVectorStore:
    def __init__(
        self,
        *,
        collection: str,  # projects/{p}/locations/{l}/collections/{c}
        data_client: DataObjectClient,
        search_client: SearchClient,
        use_sparse: bool = True,
        vertex_ranker: bool = False,
    ) -> None:
        self.collection = collection
        self._data = data_client
        self._search = search_client
        self._use_sparse = use_sparse
        self._vertex_ranker = vertex_ranker

    @classmethod
    def from_default_credentials(cls, collection: str, **kwargs: Any) -> VertexVectorStore:
        from google.cloud import vectorsearch_v1  # imported lazily: heavy, prod only

        return cls(
            collection=collection,
            data_client=vectorsearch_v1.DataObjectServiceAsyncClient(),
            search_client=vectorsearch_v1.DataObjectSearchServiceAsyncClient(),
            **kwargs,
        )

    # ── writes ────────────────────────────────────────────────────────────

    def _data_object(self, c: Chunk) -> dict[str, Any]:
        vectors: dict[str, Any] = {}
        if c.dense is not None:
            vectors["dense"] = {"dense": {"values": list(c.dense)}}
        if self._use_sparse and c.sparse is not None:
            vectors["sparse"] = {
                "sparse": {"indices": list(c.sparse.indices), "values": list(c.sparse.values)}
            }
        return {"data": {**c.payload(), "text": c.text}, "vectors": vectors}

    async def upsert(self, chunks: Sequence[Chunk]) -> None:
        from google.api_core import exceptions as gexc

        for start in range(0, len(chunks), BATCH_LIMIT):
            batch = chunks[start : start + BATCH_LIMIT]
            create = {
                "parent": self.collection,
                "requests": [
                    {"data_object_id": c.chunk_id, "data_object": self._data_object(c)}
                    for c in batch
                ],
            }
            try:
                await self._data.batch_create_data_objects(request=create)
            except (gexc.AlreadyExists, gexc.Conflict):
                # Batches are atomic: on a re-ingest, rewrite the whole batch in place.
                update = {
                    "parent": self.collection,
                    "requests": [
                        {
                            "data_object": {
                                "name": f"{self.collection}/dataObjects/{c.chunk_id}",
                                **self._data_object(c),
                            }
                        }
                        for c in batch
                    ],
                }
                await self._data.batch_update_data_objects(request=update)

    async def delete_where(self, tenant_id: str, filter: Filter) -> int:
        names: list[str] = []
        page_token = ""
        while True:
            resp = _as_mapping(
                await self._search.query_data_objects(
                    request={
                        "parent": self.collection,
                        "filter": filters.with_tenant(tenant_id, filter),
                        "page_size": BATCH_LIMIT,
                        "page_token": page_token,
                    }
                )
            )
            names.extend(obj["name"] for obj in resp.get("data_objects", []))
            page_token = resp.get("next_page_token") or ""
            if not page_token:
                break
        for start in range(0, len(names), BATCH_LIMIT):
            await self._data.batch_delete_data_objects(
                request={
                    "parent": self.collection,
                    "requests": [{"name": n} for n in names[start : start + BATCH_LIMIT]],
                }
            )
        return len(names)

    # ── search ────────────────────────────────────────────────────────────

    def build_search_request(self, req: SearchRequest) -> dict[str, Any]:
        flt = filters.with_tenant(req.tenant_id, req.filter)
        searches: list[dict[str, Any]] = []
        if req.query_dense is not None:
            searches.append(
                {
                    "vector_search": {
                        "search_field": "dense",
                        "vector": {"values": list(req.query_dense)},
                        "filter": flt,
                        "top_k": req.candidates,
                    }
                }
            )
        searches.append(
            {
                "text_search": {
                    "search_text": req.query,
                    "data_field_names": ["text", "title"],
                    "filter": flt,
                    "top_k": req.candidates,
                }
            }
        )
        if self._use_sparse and req.query_sparse is not None:
            searches.append(
                {
                    "vector_search": {
                        "search_field": "sparse",
                        "sparse_vector": {
                            "indices": list(req.query_sparse.indices),
                            "values": list(req.query_sparse.values),
                        },
                        "filter": flt,
                        "top_k": req.candidates,
                    }
                }
            )
        ranker: dict[str, Any] = {"rrf": {"weights": [1.0] * len(searches)}}
        if self._vertex_ranker:
            ranker = {
                "vertex_ranker": {
                    "model": VERTEX_RANKER_MODEL,
                    "top_n": req.candidates,
                    "text_record_spec": {
                        "query": req.query,
                        "title_template": "{title}",
                        "content_template": "{text}",
                    },
                }
            }
        return {
            "parent": self.collection,
            "searches": searches,
            "combine": {"ranker": ranker, "top_k": req.top_k},
        }

    async def search(self, req: SearchRequest) -> SearchResult:
        request = self.build_search_request(req)
        resp = _as_mapping(await self._search.batch_search_data_objects(request=request))
        lists = [r.get("results", []) for r in resp.get("results", [])]
        warnings: list[str] = []
        by_id: dict[str, Chunk] = {}
        rankings: list[list[str]] = []
        for results in lists:
            ranking = []
            for item in results:
                obj = item.get("data_object", {})
                chunk = _chunk_from_object(obj)
                if chunk.tenant_id != req.tenant_id:  # defense in depth: never leak
                    warnings.append("dropped a result from another tenant")
                    continue
                by_id[chunk.chunk_id] = chunk.without_vectors()
                ranking.append(chunk.chunk_id)
            rankings.append(ranking)
        if len(rankings) == 1:
            fused = [(cid, 1.0 / (60 + i)) for i, cid in enumerate(rankings[0], start=1)]
        else:
            fused = rrf(rankings)
        hits = [
            Hit(chunk=by_id[cid], score=score, rank=rank, signals={})
            for rank, (cid, score) in enumerate(fused[: req.top_k], start=1)
        ]
        return SearchResult(hits=hits, warnings=warnings)


def _chunk_from_object(obj: Mapping[str, Any]) -> Chunk:
    data = dict(obj.get("data", {}))
    chunk_id = obj.get("data_object_id") or str(obj.get("name", "")).rsplit("/", 1)[-1]
    heading = data.get("heading_path") or ""
    sparse = (obj.get("vectors", {}).get("sparse") or {}).get("sparse")
    return Chunk(
        chunk_id=chunk_id,
        tenant_id=data["tenant_id"],
        source_kind=data["source_kind"],
        source_id=data["source_id"],
        ordinal=int(data.get("ordinal", 0)),
        title=data.get("title", ""),
        text=data.get("text", ""),
        source=data.get("source", ""),
        doc_type=data.get("doc_type", ""),
        heading_path=tuple(h for h in heading.split(" > ") if h),
        account_id=data.get("account_id"),
        page=int(data["page"]) if data.get("page") is not None else None,
        gcs_uri=data.get("gcs_uri"),
        country=data.get("country"),
        city=data.get("city"),
        valid_from=int(data["valid_from"]) if data.get("valid_from") is not None else None,
        valid_until=int(data["valid_until"]) if data.get("valid_until") is not None else None,
        occurred_at=data.get("occurred_at"),
        sparse=SparseVector.from_dict(sparse) if sparse else None,
    )
