"""Knowledge search for ``knowledge_search`` nodes and the agent ``search_knowledge`` tool.

Delegates to ``igs_common.rag.retrieve`` (hybrid retrieval + rerank behind the VectorStore
adapter). The tenant filter is always injected here from the execution, never from flow config
or model output.
"""

from __future__ import annotations

import dataclasses
import enum
import importlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol


class Retriever(Protocol):
    async def search(
        self,
        query: str,
        *,
        tenant_id: str,
        knowledge_bases: Sequence[str],
        filters: Mapping[str, Any],
        k: int,
        rerank: bool,
    ) -> dict[str, Any]:
        """Returns ``{"hits": [{"content", "score", "citation", ...}], "citations": [...]}``."""
        ...


def to_jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dump(mode="json")
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [to_jsonable(v) for v in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _flatten_hit(hit: dict[str, Any]) -> dict[str, Any]:
    """Expose ``content`` at the top so flows can write ``hits.map(h, h.content)``."""
    raw = hit.get("chunk")
    chunk: dict[str, Any] = raw if isinstance(raw, dict) else {}
    out = dict(hit)
    out.setdefault("content", chunk.get("text") or chunk.get("content") or "")
    for key in ("source_kind", "source_id", "title", "account_id"):
        if key in chunk:
            out.setdefault(key, chunk[key])
    return out


@dataclass
class RagRetriever:
    """Production retriever: ``igs_common.rag.retrieve`` with the knowledge bases as filter."""

    options: dict[str, Any] = field(default_factory=dict)

    async def search(
        self,
        query: str,
        *,
        tenant_id: str,
        knowledge_bases: Sequence[str],
        filters: Mapping[str, Any],
        k: int,
        rerank: bool,
    ) -> dict[str, Any]:
        # Lazy: heavy deps, and only some workers search.
        retrieve = importlib.import_module("igs_common.rag").retrieve
        flt = dict(filters)
        if knowledge_bases:
            flt["knowledge_base"] = {"$in": list(knowledge_bases)}
        result = await retrieve(query, tenant_id=tenant_id, filters=flt, k=k, **self.options)
        data = to_jsonable(result)
        hits = data.get("hits", data) if isinstance(data, dict) else data
        citations = data.get("citations", []) if isinstance(data, dict) else []
        return {"hits": [_flatten_hit(h) for h in hits or []], "citations": citations}


@dataclass
class StaticRetriever:
    """Tests and offline demos: returns canned hits, records queries."""

    hits: list[dict[str, Any]] = field(default_factory=list)
    queries: list[dict[str, Any]] = field(default_factory=list)

    async def search(
        self,
        query: str,
        *,
        tenant_id: str,
        knowledge_bases: Sequence[str],
        filters: Mapping[str, Any],
        k: int,
        rerank: bool,
    ) -> dict[str, Any]:
        self.queries.append(
            {
                "query": query,
                "tenant_id": tenant_id,
                "kbs": list(knowledge_bases),
                "filters": dict(filters),
            }
        )
        hits = [_flatten_hit(h) for h in self.hits[:k]]
        return {"hits": hits, "citations": [h.get("citation") for h in hits if h.get("citation")]}
