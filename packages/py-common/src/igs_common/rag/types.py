"""Shapes shared by every vector store, embedder and reranker (docs/architecture/rag.md §6)."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal

# Agent Retrieval filter syntax ({"field": {"$op": value}}, `$and`/`$or`), at most two levels deep
# once the tenant clause is added. See `igs_common.rag.filters`.
Filter = dict[str, Any]

SourceKind = Literal["document", "interaction"]

MAX_CHUNK_ID = 63  # Agent Retrieval data object id limit


@dataclass(frozen=True, slots=True)
class SparseVector:
    indices: Sequence[int]
    values: Sequence[float]

    def as_dict(self) -> dict[str, list[float] | list[int]]:
        return {"indices": list(self.indices), "values": list(self.values)}

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> SparseVector | None:
        if not raw:
            return None
        if "indices" in raw:
            return cls(indices=list(raw["indices"]), values=list(raw["values"]))
        # `services/models` returns BGE-M3 lexical weights as {token_id: weight}.
        items = sorted((int(k), float(v)) for k, v in raw.items())
        return cls(indices=[i for i, _ in items], values=[v for _, v in items])

    def dot(self, other: SparseVector) -> float:
        weights = dict(zip(self.indices, self.values, strict=True))
        return sum(
            weights.get(i, 0.0) * v for i, v in zip(other.indices, other.values, strict=True)
        )


@dataclass(frozen=True, slots=True)
class Chunk:
    """One retrievable passage of a document or of an Account 360 interaction.

    `source_id` is the `documents.id` or `interactions.id` it came from; filter fields
    (`source`, `doc_type`, `country`, `city`, `valid_*`) are stored as payload by every store.
    """

    chunk_id: str  # <=63 chars, content-hash based (see `make_chunk_id`)
    tenant_id: str
    source_kind: SourceKind
    source_id: str
    ordinal: int
    title: str
    text: str
    source: str  # contract | policy | guide | trip_report | opponent | email | call | note …
    doc_type: str  # pdf | docx | html | text | interaction
    heading_path: tuple[str, ...] = ()
    account_id: str | None = None
    page: int | None = None
    gcs_uri: str | None = None
    country: str | None = None
    city: str | None = None
    valid_from: int | None = None  # unix days
    valid_until: int | None = None  # unix days
    occurred_at: str | None = None  # ISO timestamp, interactions only
    token_count: int = 0
    dense: Sequence[float] | None = None  # None when the store embeds by itself
    sparse: SparseVector | None = None

    def __post_init__(self) -> None:
        if not 1 <= len(self.chunk_id) <= MAX_CHUNK_ID:
            raise ValueError(f"chunk_id must be 1-{MAX_CHUNK_ID} chars: {self.chunk_id!r}")

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(f"{self.ordinal}\x1f{self.text}".encode()).hexdigest()

    def payload(self) -> dict[str, Any]:
        """Filterable/stored fields, identical across stores so filters behave the same."""
        data: dict[str, Any] = {
            "tenant_id": self.tenant_id,
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "ordinal": self.ordinal,
            "title": self.title,
            "source": self.source,
            "doc_type": self.doc_type,
            "heading_path": " > ".join(self.heading_path),
        }
        optional = {
            "account_id": self.account_id,
            "page": self.page,
            "gcs_uri": self.gcs_uri,
            "country": self.country,
            "city": self.city,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "occurred_at": self.occurred_at,
        }
        data.update({k: v for k, v in optional.items() if v is not None})
        return data

    def without_vectors(self) -> Chunk:
        return replace(self, dense=None, sparse=None)


def make_chunk_id(tenant_id: str, source_kind: str, source_id: str, ordinal: int, text: str) -> str:
    """Deterministic id: re-ingesting the same content yields the same id (idempotent upserts)."""
    digest = hashlib.sha256(
        f"{tenant_id}|{source_kind}|{source_id}|{ordinal}|{text}".encode()
    ).hexdigest()
    return "c" + digest[:40]


@dataclass(frozen=True, slots=True)
class Hit:
    chunk: Chunk
    score: float
    rank: int
    # Per-signal ranks/scores for traces and evals: {"dense": 3, "lexical": 1, "rerank": 0.92}
    signals: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SearchRequest:
    tenant_id: str
    query: str
    query_dense: Sequence[float] | None = None
    query_sparse: SparseVector | None = None
    filter: Filter = field(default_factory=dict)
    top_k: int = 8
    candidates: int = 50  # per sub-search, before fusion


@dataclass(frozen=True, slots=True)
class SearchResult:
    hits: list[Hit]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Citation:
    """What the agent and the UI get for an `[n]` marker."""

    n: int
    chunk_id: str
    source_kind: SourceKind
    source_id: str
    title: str
    heading_path: str
    snippet: str
    account_id: str | None = None
    page: int | None = None
    gcs_uri: str | None = None
    occurred_at: str | None = None


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    query: str
    hits: list[Hit]
    citations: list[Citation]
    reranked: bool
    warnings: list[str] = field(default_factory=list)

    def context(self, max_chars_per_hit: int = 1200) -> str:
        """Numbered passages for the model prompt; markers match `citations[i].n`."""
        blocks = []
        for c, h in zip(self.citations, self.hits, strict=True):
            where = " > ".join(x for x in (c.title, c.heading_path) if x)
            dated = f" ({c.occurred_at[:10]})" if c.occurred_at else ""
            blocks.append(f"[{c.n}] {where}{dated}\n{h.chunk.text[:max_chars_per_hit]}")
        return "\n\n".join(blocks)
